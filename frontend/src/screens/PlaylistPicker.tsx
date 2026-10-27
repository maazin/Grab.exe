import { useState } from 'react'
import type { Preset, ProbeResult } from '../api'
import { Sheet } from '../components/Sheet'
import { Button, Tag } from '../components/ui'
import { clock, PRESET_TAG } from '../format'

export function PlaylistPicker({
  open,
  info,
  preset,
  busy,
  error,
  onClose,
  onSubmit,
}: {
  open: boolean
  info: ProbeResult
  preset: Preset
  busy: boolean
  error: string | null
  onClose: () => void
  onSubmit: (ids: string[]) => void
}) {
  const [checked, setChecked] = useState<Set<string>>(() => new Set(info.entries.map((e) => e.video_id)))
  const all = checked.size === info.entries.length
  const toggle = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <Sheet
      open={open}
      onClose={onClose}
      label="Playlist"
      status={PRESET_TAG[preset]}
      footer={
        <div className="space-y-3">
          {error && (
            <p role="alert" className="flex gap-2 text-error">
              <Tag tone="error">ERROR</Tag>
              <span>{error}</span>
            </p>
          )}
          <Button
            variant="primary"
            className="w-full"
            disabled={busy || checked.size === 0}
            onClick={() => onSubmit(info.entries.filter((e) => checked.has(e.video_id)).map((e) => e.video_id))}
          >
            {busy ? 'Adding…' : `Add ${checked.size} to queue`}
          </Button>
        </div>
      }
    >
      <p className="mb-3 line-clamp-2 text-[16px] font-semibold">{info.title}</p>
      <label className="flex min-h-11 cursor-pointer items-center gap-3 border-b-[1.5px] border-line pb-2">
        <input
          type="checkbox"
          checked={all}
          ref={(el) => {
            if (el) el.indeterminate = !all && checked.size > 0
          }}
          onChange={() => setChecked(all ? new Set() : new Set(info.entries.map((e) => e.video_id)))}
          className="size-5 accent-[var(--accent)]"
        />
        <span className="label">Select all</span>
        <span className="num ml-auto text-muted">
          {checked.size}/{info.entries.length}
        </span>
      </label>
      <ul className="divide-y divide-line/20">
        {info.entries.map((e, i) => (
          <li key={e.video_id}>
            <label className="flex min-h-11 cursor-pointer items-center gap-3 py-2">
              <input
                type="checkbox"
                checked={checked.has(e.video_id)}
                onChange={() => toggle(e.video_id)}
                className="size-5 shrink-0 accent-[var(--accent)]"
              />
              <span className="num w-7 shrink-0 text-muted">{String(i + 1).padStart(2, '0')}</span>
              <span className="min-w-0 flex-1 truncate">{e.title}</span>
              <span className="num shrink-0 text-muted">{clock(e.duration_s)}</span>
            </label>
          </li>
        ))}
      </ul>
    </Sheet>
  )
}
