import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, type SystemInfo } from '../api'
import { Sheet } from '../components/Sheet'
import { Button, Spinner, Tag, Toggle } from '../components/ui'
import { bytes } from '../format'
import { applyTheme, load, save, type Theme } from '../prefs'

type Update =
  | { name: 'idle' }
  | { name: 'running' }
  | { name: 'restarting'; from: string; to: string }
  | { name: 'done'; from: string; to: string }
  | { name: 'error'; message: string }

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

export function Settings({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [info, setInfo] = useState<SystemInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [update, setUpdate] = useState<Update>({ name: 'idle' })
  const [theme, setTheme] = useState<Theme>(() => load<Theme>('theme', 'system'))

  const refresh = useCallback(() => {
    api
      .system()
      .then((s) => {
        setInfo(s)
        setError(null)
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load system info.'))
  }, [])

  useEffect(() => {
    if (open) refresh()
  }, [open, refresh])

  const runUpdate = async () => {
    setUpdate({ name: 'running' })
    try {
      const r = await api.updateYtdlp()
      if (!r.restarting) {
        setUpdate({ name: 'done', from: r.old_version, to: r.new_version })
        refresh()
        return
      }
      setUpdate({ name: 'restarting', from: r.old_version, to: r.new_version })
      // The app exits and Docker brings it back; wait for it to answer again.
      await wait(2500)
      for (let i = 0; i < 60; i++) {
        try {
          const s = await api.system()
          setInfo(s)
          setUpdate({ name: 'done', from: r.old_version, to: s.ytdlp_version })
          return
        } catch {
          await wait(1000)
        }
      }
      setUpdate({ name: 'error', message: 'Grab did not come back after restarting. Check the home machine.' })
    } catch (e) {
      setUpdate({ name: 'error', message: e instanceof ApiError ? e.message : 'Update failed.' })
    }
  }

  const rows: [string, string][] = info
    ? [
        ['yt-dlp', info.ytdlp_version],
        ['ffmpeg', info.ffmpeg_version ?? 'not found'],
        ['Grab', info.app_version],
        ['Free disk', bytes(info.disk_free_bytes)],
        ['Downloads', bytes(info.downloads_bytes)],
      ]
    : []

  return (
    <Sheet open={open} onClose={onClose} label="Settings">
      <div className="space-y-5">
        <section aria-label="System">
          <h3 className="label mb-2 text-muted">System</h3>
          {error && (
            <p role="alert" className="flex gap-2 text-error">
              <Tag tone="error">ERROR</Tag>
              <span>{error}</span>
            </p>
          )}
          {!info && !error && <Spinner />}
          {info && (
            <dl className="divide-y-[1.5px] divide-line/15">
              {rows.map(([k, v]) => (
                <div key={k} className="flex min-h-10 items-center justify-between gap-4">
                  <dt>{k}</dt>
                  <dd className="num truncate text-muted">{v}</dd>
                </div>
              ))}
            </dl>
          )}
        </section>

        <section aria-label="Update yt-dlp" className="space-y-2">
          <Button
            className="w-full"
            onClick={runUpdate}
            disabled={update.name === 'running' || update.name === 'restarting'}
          >
            {update.name === 'running' ? 'Updating yt-dlp…' : update.name === 'restarting' ? 'Restarting…' : 'Update yt-dlp'}
          </Button>
          <p className="text-[14px] text-muted" role="status">
            {update.name === 'idle' && 'Fixes most download failures after YouTube changes something.'}
            {update.name === 'running' && 'Installing the latest yt-dlp. This can take a minute.'}
            {update.name === 'restarting' && `Installed ${update.to} (was ${update.from}). Restarting Grab…`}
            {update.name === 'done' &&
              (update.from === update.to ? `Already on the latest version, ${update.to}.` : `Updated ${update.from} → ${update.to}.`)}
            {update.name === 'error' && <span className="text-error">{update.message}</span>}
          </p>
        </section>

        <section aria-label="Theme" className="space-y-2">
          <h3 className="label text-muted">Theme</h3>
          <Toggle
            label="Theme"
            value={theme}
            onChange={(t) => {
              setTheme(t)
              save('theme', t)
              applyTheme(t)
            }}
            options={[
              { value: 'system', label: 'System' },
              { value: 'light', label: 'Light' },
              { value: 'dark', label: 'Dark' },
            ]}
          />
        </section>
      </div>
    </Sheet>
  )
}
