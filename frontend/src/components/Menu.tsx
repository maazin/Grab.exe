import { useEffect, useId, useRef, useState } from 'react'

export interface MenuItem {
  label: string
  onSelect?: () => void
  href?: string
  danger?: boolean
}

/* The ⋯ menu on history rows. */
export function Menu({ items, label }: { items: MenuItem[]; label: string }) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const id = useId()

  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        root.current?.querySelector<HTMLButtonElement>('button')?.focus()
      }
    }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    root.current?.querySelector<HTMLElement>('[role=menuitem]')?.focus()
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const move = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    e.preventDefault()
    const els = [...(root.current?.querySelectorAll<HTMLElement>('[role=menuitem]') ?? [])]
    const i = els.indexOf(document.activeElement as HTMLElement)
    els[(i + (e.key === 'ArrowDown' ? 1 : -1) + els.length) % els.length]?.focus()
  }

  const itemClass = (danger?: boolean) =>
    `flex min-h-11 w-full items-center px-3 text-left text-[15px] hover:bg-ink/5 focus-visible:bg-ink/5 ${danger ? 'text-error' : ''}`

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className="num inline-flex min-h-11 min-w-11 items-center justify-center rounded-[4px] text-[18px] hover:bg-ink/5"
      >
        ⋯
      </button>
      {open && (
        <div id={id} role="menu" onKeyDown={move} className="frame shadow-hard absolute right-0 top-full z-20 mt-1 min-w-40 bg-surface py-1">
          {items.map((item) =>
            item.href ? (
              <a key={item.label} role="menuitem" href={item.href} download onClick={() => setOpen(false)} className={itemClass(item.danger)}>
                {item.label}
              </a>
            ) : (
              <button
                key={item.label}
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false)
                  item.onSelect?.()
                }}
                className={itemClass(item.danger)}
              >
                {item.label}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  )
}
