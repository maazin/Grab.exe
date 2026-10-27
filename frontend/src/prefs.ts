// Per-device conveniences. Storage can be missing or throw (private mode), so every access is guarded.

export function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(`grab:${key}`)
    return raw == null ? fallback : (JSON.parse(raw) as T)
  } catch {
    return fallback
  }
}

export function save(key: string, value: unknown): void {
  try {
    localStorage.setItem(`grab:${key}`, JSON.stringify(value))
  } catch {
    // ignore
  }
}

export type Theme = 'system' | 'light' | 'dark'

export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  if (theme === 'system') delete root.dataset.theme
  else root.dataset.theme = theme
}
