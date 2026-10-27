import type { Preset } from './api'

export function bytes(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n < 1024) return `${n} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let v = n / 1024
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v >= 100 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`
}

export function speed(bps: number | null | undefined): string {
  return bps ? `${bytes(bps)}/s` : '—'
}

export function clock(seconds: number | null | undefined): string {
  if (seconds == null || !isFinite(seconds)) return '—'
  const s = Math.max(0, Math.round(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

export function stamp(iso: string): string {
  const d = new Date(iso)
  const time = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  const sameYear = d.getFullYear() === new Date().getFullYear()
  return `${MONTHS[d.getMonth()]} ${d.getDate()}${sameYear ? '' : ` ${d.getFullYear()}`} · ${time}`
}

export const PRESET_TAG: Record<Preset, string> = {
  video_best: 'MP4 BEST',
  video_1080: 'MP4 1080P',
  video_720: 'MP4 720P',
  audio_mp3: 'MP3',
  audio_m4a: 'M4A',
}

export type Kind = 'video' | 'audio'

export const QUALITIES: Record<Kind, { preset: Preset; label: string; hint: string }[]> = {
  video: [
    { preset: 'video_best', label: 'Best', hint: 'Highest resolution. May be VP9 or AV1, which some iPhone apps won’t play.' },
    { preset: 'video_1080', label: '1080p', hint: 'H.264 + AAC. Plays anywhere.' },
    { preset: 'video_720', label: '720p', hint: 'H.264 + AAC. Smaller file, faster away from home.' },
  ],
  audio: [
    { preset: 'audio_mp3', label: 'MP3', hint: '192 kbps with cover art and title.' },
    { preset: 'audio_m4a', label: 'M4A', hint: 'Original audio, no re-encode. Cover art and title.' },
  ],
}
