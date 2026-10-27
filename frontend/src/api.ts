export type Status = 'queued' | 'downloading' | 'converting' | 'done' | 'failed' | 'canceled' | 'expired'
export type Preset = 'video_best' | 'video_1080' | 'video_720' | 'audio_mp3' | 'audio_m4a'

export interface Job {
  id: string
  url: string
  video_id: string
  title: string
  uploader: string | null
  duration_s: number | null
  thumbnail_url: string | null
  preset: Preset
  status: Status
  progress_pct: number
  downloaded_bytes: number | null
  total_bytes: number | null
  speed_bps: number | null
  eta_s: number | null
  file_path: string | null
  file_name: string | null
  file_size_bytes: number | null
  error_code: string | null
  error_message: string | null
  created_at: string
  finished_at: string | null
  expires_at: string | null
}

export interface ProbeEntry {
  video_id: string
  title: string
  duration_s: number | null
}

export interface ProbeResult {
  video_id: string
  title: string
  uploader: string | null
  duration_s: number | null
  thumbnail_url: string | null
  is_playlist: boolean
  entries: ProbeEntry[]
}

export interface SystemInfo {
  ytdlp_version: string
  ffmpeg_version: string | null
  app_version: string
  disk_free_bytes: number
  downloads_bytes: number
}

export const ACTIVE: Status[] = ['queued', 'downloading', 'converting']
export const isActive = (s: Status) => ACTIVE.includes(s)

export class ApiError extends Error {
  code: string
  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'same-origin',
    })
  } catch {
    // An expired Cloudflare Access session redirects to its login page, which fetch can't follow.
    throw new ApiError('network', "Can't reach Grab. Check your connection, or reload the page to sign in again.")
  }
  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const err = data?.error
    throw new ApiError(err?.code ?? 'unknown', err?.message ?? `Request failed (${res.status}).`)
  }
  return data as T
}

export const api = {
  probe: (url: string) => request<ProbeResult>('POST', '/api/probe', { url }),
  createJobs: (url: string, preset: Preset, video_ids?: string[]) =>
    request<{ jobs: Job[] }>('POST', '/api/jobs', { url, preset, video_ids }),
  jobs: (status?: 'active') => request<{ jobs: Job[] }>('GET', `/api/jobs${status ? `?status=${status}` : ''}`),
  cancel: (id: string) => request<Job>('POST', `/api/jobs/${id}/cancel`),
  retry: (id: string) => request<Job>('POST', `/api/jobs/${id}/retry`),
  remove: (id: string) => request<void>('DELETE', `/api/jobs/${id}`),
  history: (q: string, limit: number, offset: number) =>
    request<{ jobs: Job[]; total: number }>(
      'GET',
      `/api/history?${new URLSearchParams({ q, limit: String(limit), offset: String(offset) })}`,
    ),
  system: () => request<SystemInfo>('GET', '/api/system'),
  updateYtdlp: () =>
    request<{ old_version: string; new_version: string; restarting: boolean }>('POST', '/api/system/update-ytdlp'),
}

export const fileUrl = (id: string) => `/api/files/${id}`
