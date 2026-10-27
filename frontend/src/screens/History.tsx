import { useEffect, useMemo, useState, type Dispatch } from 'react'
import { api, ApiError, fileUrl, type Job } from '../api'
import { jobActions } from '../actions'
import { Menu, type MenuItem } from '../components/Menu'
import { Button, Card, Spinner, Tag } from '../components/ui'
import { bytes, PRESET_TAG, stamp } from '../format'
import type { Action } from '../store'
import { statusTag } from './Queue'

const PAGE = 50

export function History({ jobs, dispatch }: { jobs: Record<string, Job>; dispatch: Dispatch<Action> }) {
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [ids, setIds] = useState<string[]>([])
  const [total, setTotal] = useState(0)
  const [loadedKey, setLoadedKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const actions = useMemo(() => jobActions(dispatch), [dispatch])

  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(q.trim())
      setOffset(0)
    }, 250)
    return () => clearTimeout(t)
  }, [q])

  const key = `${query}|${offset}|${reload}`
  const loading = loadedKey !== key

  useEffect(() => {
    let live = true
    api
      .history(query, PAGE, offset)
      .then((res) => {
        if (!live) return
        dispatch({ type: 'upsert', jobs: res.jobs })
        setIds(res.jobs.map((j) => j.id))
        setTotal(res.total)
        setError(null)
      })
      .catch((e) => live && setError(e instanceof ApiError ? e.message : 'Could not load history.'))
      .finally(() => live && setLoadedKey(`${query}|${offset}|${reload}`))
    return () => {
      live = false
    }
  }, [query, offset, reload, dispatch])

  // Rows come from the shared store so live events (done, expired) update them in place.
  const rows = ids.map((id) => jobs[id]).filter(Boolean)

  const getAgain = async (id: string) => {
    await actions.retry(id)
    setReload((n) => n + 1) // the new job becomes the top row
  }

  return (
    <Card label="History" status={loading ? <Spinner /> : `${total} ${total === 1 ? 'job' : 'jobs'}`}>
      <label htmlFor="history-search" className="sr-only">
        Search by title
      </label>
      <input
        id="history-search"
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search by title"
        autoComplete="off"
        enterKeyHint="search"
        className="frame h-12 w-full bg-surface px-3 text-[15px] placeholder:text-muted"
      />

      {error && (
        <p role="alert" className="mt-3 flex gap-2 text-error">
          <Tag tone="error">ERROR</Tag>
          <span>{error}</span>
        </p>
      )}

      {!loading && !error && rows.length === 0 && (
        <p className="mt-6 text-center text-muted">{query ? 'Nothing matches that title.' : 'Nothing grabbed yet.'}</p>
      )}

      <ul className="mt-2 divide-y-[1.5px] divide-line/15">
        {rows.map((job) => {
          const tag = statusTag(job)
          const items: MenuItem[] = []
          if (job.status === 'done') items.push({ label: 'Save', href: fileUrl(job.id) })
          if (job.status === 'expired' || job.status === 'failed' || job.status === 'canceled')
            items.push({ label: 'Get again', onSelect: () => getAgain(job.id) })
          items.push({
            label: 'Delete',
            danger: true,
            onSelect: () => {
              actions.remove(job.id).then(() => {
                setIds((prev) => prev.filter((x) => x !== job.id))
                setTotal((t) => Math.max(0, t - 1))
              })
            },
          })
          return (
            <li key={job.id} className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="num text-muted">{stamp(job.created_at)}</p>
                <p className="mt-0.5 truncate font-semibold" title={job.title}>
                  {job.title}
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <Tag tone={tag.tone}>{tag.text}</Tag>
                  <Tag tone="muted">{PRESET_TAG[job.preset]}</Tag>
                  {job.file_size_bytes != null && <span className="num text-muted">{bytes(job.file_size_bytes)}</span>}
                </div>
              </div>
              {job.status === 'expired' && (
                <Button size="sm" onClick={() => getAgain(job.id)}>
                  Get again
                </Button>
              )}
              <Menu label={`Actions for ${job.title}`} items={items} />
            </li>
          )
        })}
      </ul>

      {total > PAGE && (
        <nav className="mt-3 flex items-center justify-between gap-3 border-t-[1.5px] border-line pt-3" aria-label="Pages">
          <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
            Newer
          </Button>
          <span className="num text-muted">
            {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
          </span>
          <Button size="sm" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
            Older
          </Button>
        </nav>
      )}
    </Card>
  )
}
