import { useEffect, useLayoutEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'

const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' ')

/* Card with a thin label strip on top. `raised` adds the hard shadow (main card only). */
export function Card({
  label,
  status,
  raised,
  children,
  className,
}: {
  label: string
  status?: ReactNode
  raised?: boolean
  children: ReactNode
  className?: string
}) {
  return (
    <section className={cx('frame bg-surface', raised && 'shadow-hard', className)} aria-label={label}>
      <header className="flex h-8 items-center justify-between gap-3 border-b-[1.5px] border-line px-3">
        <h2 className="label">{label}</h2>
        {status != null && <span className="label truncate text-muted">{status}</span>}
      </header>
      <div className="p-4">{children}</div>
    </section>
  )
}

type Variant = 'primary' | 'secondary' | 'ghost'

const BUTTON: Record<Variant, string> = {
  primary: 'frame press bg-accent text-on-accent font-semibold',
  secondary: 'frame bg-surface text-ink font-medium hover:bg-ink/5',
  ghost: 'text-ink font-medium hover:bg-ink/5 rounded-[4px]',
}

export function buttonClass(variant: Variant = 'secondary', size: 'md' | 'sm' = 'md', extra?: string) {
  return cx(
    'inline-flex select-none items-center justify-center gap-2 whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50',
    size === 'md' ? 'min-h-11 px-4 text-[15px]' : 'min-h-11 px-3 text-[14px]',
    BUTTON[variant],
    extra,
  )
}

export function Button({
  variant = 'secondary',
  size = 'md',
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'md' | 'sm' }) {
  return <button type="button" className={buttonClass(variant, size, className)} {...props} />
}

/* Segmented control: one choice of a few, e.g. VIDEO / AUDIO or System / Light / Dark. */
export function Toggle<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T
  options: { value: T; label: string }[]
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className="frame grid overflow-hidden" style={{ gridTemplateColumns: `repeat(${options.length}, 1fr)` }}>
      {options.map((o, i) => {
        const on = o.value === value
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            onKeyDown={(e) => {
              const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0
              if (!step) return
              e.preventDefault()
              const next = options[(i + step + options.length) % options.length]
              onChange(next.value)
              ;(e.currentTarget.parentElement?.children[options.indexOf(next)] as HTMLElement | undefined)?.focus()
            }}
            tabIndex={on ? 0 : -1}
            className={cx(
              'label min-h-11 -outline-offset-4 transition-colors duration-[120ms]',
              i > 0 && 'border-l-[1.5px] border-line',
              on ? 'bg-ink text-surface' : 'bg-surface text-ink hover:bg-ink/5',
            )}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

export function Chip({ selected, children, onClick }: { selected: boolean; children: ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={cx(
        'frame label min-h-11 min-w-16 px-3 transition-colors duration-[120ms]',
        selected ? 'bg-ink text-surface' : 'bg-surface text-ink hover:bg-ink/5',
      )}
    >
      {children}
    </button>
  )
}

export type Tone = 'ink' | 'muted' | 'error'

/* Bracket tag like [DONE] or [42%]. */
export function Tag({ children, tone = 'ink' }: { children: ReactNode; tone?: Tone }) {
  const color = tone === 'error' ? 'text-error' : tone === 'muted' ? 'text-muted' : 'text-ink'
  return <span className={cx('label shrink-0 whitespace-nowrap', color)}>[{children}]</span>
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false)
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!mq) return
    const on = () => setReduced(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return reduced
}

const BLOCK = 8
const GAP = 2

/* Square 8 px blocks that fill one at a time. `sweep` shows one block running across (ffmpeg stage). */
export function SegmentedBar({
  pct,
  sweep,
  tone = 'accent',
  label,
}: {
  pct: number
  sweep?: boolean
  tone?: 'accent' | 'muted' | 'error'
  label: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [count, setCount] = useState(40)
  const [pos, setPos] = useState(0)
  const reduced = useReducedMotion()

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => setCount(Math.max(8, Math.floor((el.clientWidth + GAP) / (BLOCK + GAP))))
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    if (!sweep || reduced) return
    const t = setInterval(() => setPos((p) => (p + 1) % count), 60)
    return () => clearInterval(t)
  }, [sweep, reduced, count])

  const clamped = Math.max(0, Math.min(100, pct))
  const filled = Math.round((clamped / 100) * count)
  const fill = tone === 'error' ? 'bg-error' : tone === 'muted' ? 'bg-muted' : 'bg-accent'

  return (
    <div
      ref={ref}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(sweep ? 100 : clamped)}
      aria-valuetext={sweep ? 'Converting' : `${Math.round(clamped)}%`}
      className="flex h-2 overflow-hidden"
      style={{ gap: GAP }}
    >
      {Array.from({ length: count }, (_, i) => {
        const on = sweep ? reduced || i === pos : i < filled
        return <span key={i} className={cx('h-2 w-2 shrink-0', on ? fill : 'bg-ink/12')} />
      })}
    </div>
  )
}

export function Spinner() {
  return <span className="num cursor-blink" aria-hidden>▮</span>
}

export function IconButton({ label, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-[4px] text-ink hover:bg-ink/5"
      {...props}
    >
      {children}
    </button>
  )
}

export function SettingsIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12" strokeLinecap="square" />
      <rect x="14" y="4" width="4" height="4" />
      <rect x="8" y="10" width="4" height="4" />
      <rect x="16" y="16" width="4" height="4" />
    </svg>
  )
}

export { cx }
