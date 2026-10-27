import { useRef, useState, type Dispatch } from 'react'
import { api, ApiError, type Preset, type ProbeResult } from '../api'
import { Button, Card, Chip, Spinner, Tag, Toggle, cx } from '../components/ui'
import { clock, QUALITIES, type Kind } from '../format'
import { load, save } from '../prefs'
import type { Action } from '../store'
import { PlaylistPicker } from './PlaylistPicker'

type Phase = { name: 'idle' } | { name: 'probing' } | { name: 'ready'; info: ProbeResult; url: string } | { name: 'error'; message: string }

const looksLikeLink = (s: string) => /youtu\.?be|^https?:\/\//i.test(s.trim())

export function GrabCard({ dispatch }: { dispatch: Dispatch<Action> }) {
  const [url, setUrl] = useState('')
  const [phase, setPhase] = useState<Phase>({ name: 'idle' })
  const [kind, setKindState] = useState<Kind>(() => load<Kind>('kind', 'video'))
  const [quality, setQuality] = useState<Record<Kind, Preset>>(() =>
    load('quality', { video: 'video_1080', audio: 'audio_mp3' } as Record<Kind, Preset>),
  )
  const [busy, setBusy] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const probeSeq = useRef(0)

  const preset = quality[kind]
  const setKind = (k: Kind) => {
    setKindState(k)
    save('kind', k)
  }
  const choose = (p: Preset) => {
    const next = { ...quality, [kind]: p }
    setQuality(next)
    save('quality', next)
  }

  const probe = async (raw: string) => {
    const link = raw.trim()
    if (!link) return
    const seq = ++probeSeq.current
    setPhase({ name: 'probing' })
    setSubmitError(null)
    try {
      const info = await api.probe(link)
      if (seq !== probeSeq.current) return
      setPhase({ name: 'ready', info, url: link })
      if (info.is_playlist) setPickerOpen(true)
    } catch (e) {
      if (seq !== probeSeq.current) return
      setPhase({ name: 'error', message: e instanceof ApiError ? e.message : 'Something went wrong.' })
    }
  }

  const reset = () => {
    probeSeq.current++
    setUrl('')
    setPhase({ name: 'idle' })
    setPickerOpen(false)
    input.current?.focus()
  }

  const queue = async (videoIds?: string[]) => {
    if (phase.name !== 'ready') return
    setBusy(true)
    setSubmitError(null)
    try {
      const { jobs } = await api.createJobs(phase.url, preset, videoIds)
      dispatch({ type: 'upsert', jobs })
      const ready = jobs.filter((j) => j.status === 'done')
      if (ready.length === 1 && jobs.length === 1) dispatch({ type: 'toast', text: ready[0].title, jobId: ready[0].id })
      setPickerOpen(false)
      reset()
    } catch (e) {
      setSubmitError(e instanceof ApiError ? e.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  const pasteFromClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText()
      if (text) {
        setUrl(text.trim())
        probe(text)
      }
    } catch {
      input.current?.focus()
    }
  }

  const status =
    phase.name === 'probing' ? 'FETCHING' : phase.name === 'error' ? 'ERROR' : phase.name === 'ready' ? (phase.info.is_playlist ? 'PLAYLIST' : 'READY') : 'IDLE'
  const error = phase.name === 'error' ? phase.message : submitError
  const info = phase.name === 'ready' ? phase.info : null
  const qualities = QUALITIES[kind]
  const hint = qualities.find((q) => q.preset === preset)?.hint
  const canClipboard = typeof navigator !== 'undefined' && !!navigator.clipboard?.readText

  return (
    <Card label="New grab" status={status} raised>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          probe(url)
        }}
      >
        <label htmlFor="link" className="sr-only">
          YouTube link
        </label>
        <div className="frame flex min-h-12 items-center bg-surface focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent">
          <div className="relative min-w-0 flex-1">
            <input
              ref={input}
              id="link"
              type="url"
              inputMode="url"
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              enterKeyHint="go"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value)
                if (!e.target.value) setPhase({ name: 'idle' })
              }}
              onPaste={(e) => {
                const text = e.clipboardData.getData('text')
                if (looksLikeLink(text)) {
                  e.preventDefault()
                  setUrl(text.trim())
                  probe(text)
                }
              }}
              aria-invalid={phase.name === 'error'}
              aria-describedby={error ? 'link-error' : undefined}
              className={cx(
                'h-12 w-full bg-transparent px-3 text-[15px] text-ink outline-none',
                !url && '[caret-color:transparent]',
              )}
            />
            {!url && (
              <span aria-hidden className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-muted">
                Paste a YouTube link
                <span className="cursor-blink ml-1 inline-block h-[1.1em] w-[0.55em] bg-ink" />
              </span>
            )}
          </div>
          {phase.name === 'probing' ? (
            <span className="px-4">
              <Spinner />
            </span>
          ) : url ? (
            <button type="button" onClick={reset} className="label min-h-11 px-3 text-muted hover:text-ink" aria-label="Clear link">
              [CLEAR]
            </button>
          ) : (
            canClipboard && (
              <button type="button" onClick={pasteFromClipboard} className="label min-h-11 px-3 hover:bg-ink/5">
                [PASTE]
              </button>
            )
          )}
        </div>
      </form>

      {error && (
        <p id="link-error" role="alert" className="mt-3 flex gap-2 text-error">
          <Tag tone="error">ERROR</Tag>
          <span>{error}</span>
        </p>
      )}

      {info && (
        <div className="mt-4 space-y-4">
          <div className="flex gap-3">
            {info.thumbnail_url && (
              <img
                src={info.thumbnail_url}
                alt=""
                referrerPolicy="no-referrer"
                className="frame aspect-video w-28 shrink-0 bg-ink/5 object-cover sm:w-36"
              />
            )}
            <div className="min-w-0">
              <p className="line-clamp-2 text-[16px] font-semibold leading-snug">{info.title}</p>
              <p className="mt-1 truncate text-muted">{info.uploader ?? 'Unknown channel'}</p>
              <p className="num mt-1 text-muted">
                {info.is_playlist ? `${info.entries.length} VIDEOS` : clock(info.duration_s)}
              </p>
            </div>
          </div>

          <Toggle
            label="Download type"
            value={kind}
            onChange={setKind}
            options={[
              { value: 'video', label: 'Video' },
              { value: 'audio', label: 'Audio' },
            ]}
          />

          <div>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Quality">
              {qualities.map((q) => (
                <Chip key={q.preset} selected={q.preset === preset} onClick={() => choose(q.preset)}>
                  {q.label}
                </Chip>
              ))}
            </div>
            {hint && <p className="mt-2 text-[14px] text-muted">{hint}</p>}
          </div>

          {info.is_playlist ? (
            <Button variant="primary" className="w-full" onClick={() => setPickerOpen(true)}>
              Choose videos…
            </Button>
          ) : (
            <Button variant="primary" className="w-full" disabled={busy} onClick={() => queue()}>
              {busy ? 'Adding…' : 'Download'}
            </Button>
          )}
        </div>
      )}

      {info?.is_playlist && (
        <PlaylistPicker
          open={pickerOpen}
          info={info}
          preset={preset}
          busy={busy}
          error={submitError}
          onClose={() => setPickerOpen(false)}
          onSubmit={(ids) => queue(ids)}
        />
      )}
    </Card>
  )
}
