import { useEffect, useMemo, useState, type Dispatch } from 'react'
import { fileUrl, isActive, type Job } from '../api'
import { jobActions } from '../actions'
import { Button, buttonClass, Card, SegmentedBar, Tag, type Tone } from '../components/ui'
import { bytes, clock, PRESET_TAG, speed } from '../format'
import type { Action } from '../store'

const RECENT_MS = 2 * 60 * 60 * 1000
const MAX_RECENT = 8

export function statusTag(job: Job): { text: string; tone: Tone } {
  switch (job.status) {
    case 'queued':
      return { text: 'QUEUED', tone: 'muted' }
    case 'downloading':
      return { text: `${Math.floor(job.progress_pct)}%`, tone: 'ink' }
    case 'converting':
      return { text: 'CONVERTING', tone: 'ink' }
    case 'done':
      return { text: 'DONE', tone: 'ink' }
    case 'failed':
      return { text: 'FAILED', tone: 'error' }
    case 'canceled':
      return { text: 'CANCELED', tone: 'muted' }
    case 'expired':
      return { text: 'EXPIRED', tone: 'muted' }
  }
}

function detail(job: Job): string {
  switch (job.status) {
    case 'queued':
      return 'Waiting'
    case 'downloading': {
      const parts = [`${Math.floor(job.progress_pct)}%`]
      if (job.speed_bps) parts.push(speed(job.speed_bps))
      if (job.eta_s != null) parts.push(`${clock(job.eta_s)} left`)
      return parts.join(' · ')
    }
    case 'converting':
      return 'CONVERTING'
    case 'done':
      return bytes(job.file_size_bytes)
    case 'failed':
      return job.error_message ?? 'Failed'
    case 'canceled':
      return 'Canceled'
    case 'expired':
      return 'Expired'
  }
}

export function SaveLink({ job, size = 'sm' }: { job: Job; size?: 'sm' | 'md' }) {
  return (
    <a href={fileUrl(job.id)} download={job.file_name ?? true} className={buttonClass('secondary', size)}>
      Save
    </a>
  )
}

function QueueRow({ job, actions }: { job: Job; actions: ReturnType<typeof jobActions> }) {
  const tag = statusTag(job)
  const pct = job.status === 'done' ? 100 : job.status === 'queued' ? 0 : job.progress_pct
  const tone = job.status === 'failed' ? 'error' : job.status === 'canceled' || job.status === 'expired' ? 'muted' : 'accent'
  return (
    <li className="space-y-2 py-3 first:pt-0 last:pb-0">
      <div className="flex items-center gap-3">
        <p className="min-w-0 flex-1 truncate text-[16px] font-semibold" title={job.title}>
          {job.title}
        </p>
        <Tag tone="muted">{PRESET_TAG[job.preset]}</Tag>
      </div>
      <SegmentedBar pct={pct} sweep={job.status === 'converting'} tone={tone} label={`${job.title} progress`} />
      <div className="flex items-center gap-3">
        <Tag tone={tag.tone}>{tag.text}</Tag>
        <p className={`num min-w-0 flex-1 truncate ${job.status === 'failed' ? 'text-error' : 'text-muted'}`} aria-live="off">
          {detail(job)}
        </p>
        {isActive(job.status) ? (
          <Button size="sm" onClick={() => actions.cancel(job.id)}>
            Cancel
          </Button>
        ) : job.status === 'done' ? (
          <SaveLink job={job} />
        ) : (
          <Button size="sm" onClick={() => actions.retry(job.id)}>
            {job.status === 'expired' ? 'Get again' : 'Retry'}
          </Button>
        )}
      </div>
    </li>
  )
}

export function Queue({ jobs, dispatch }: { jobs: Record<string, Job>; dispatch: Dispatch<Action> }) {
  const actions = useMemo(() => jobActions(dispatch), [dispatch])
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(t)
  }, [])
  const rows = useMemo(() => {
    const all = Object.values(jobs).sort((a, b) => b.created_at.localeCompare(a.created_at))
    const active = all.filter((j) => isActive(j.status)).reverse() // oldest first: the order they'll run
    const cutoff = now - RECENT_MS
    const recent = all
      .filter((j) => !isActive(j.status) && j.status !== 'expired')
      .filter((j) => new Date(j.finished_at ?? j.created_at).getTime() > cutoff)
      .slice(0, MAX_RECENT)
    return [...active, ...recent]
  }, [jobs, now])

  if (rows.length === 0) return null
  const activeCount = rows.filter((j) => isActive(j.status)).length

  return (
    <Card label="Queue" status={activeCount ? `${activeCount} active` : 'Idle'}>
      <ul className="divide-y-[1.5px] divide-line/15">{rows.map((j) => <QueueRow key={j.id} job={j} actions={actions} />)}</ul>
    </Card>
  )
}
