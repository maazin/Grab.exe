import { useEffect, useRef, type ReactNode } from 'react'

/* Bottom sheet on phones, centered modal on desktop. Native <dialog> handles focus trapping and Esc. */
export function Sheet({
  open,
  onClose,
  label,
  status,
  children,
  footer,
}: {
  open: boolean
  onClose: () => void
  label: string
  status?: ReactNode
  children: ReactNode
  footer?: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      aria-label={label}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose() // click on the backdrop
      }}
      className="anim-sheet frame m-0 mt-auto max-h-[85dvh] w-full max-w-none overflow-hidden border-b-0 bg-surface p-0 text-ink sm:m-auto sm:max-h-[80dvh] sm:w-[560px] sm:border-b-[1.5px] sm:shadow-hard"
    >
      {open && (
        <div className="flex max-h-[inherit] flex-col">
          <header className="flex h-11 shrink-0 items-center justify-between gap-3 border-b-[1.5px] border-line pl-3">
            <h2 className="label">{label}</h2>
            <div className="flex items-center gap-1">
              {status != null && <span className="label text-muted">{status}</span>}
              <button type="button" onClick={onClose} className="label min-h-11 px-3 -outline-offset-2 hover:bg-ink/5" aria-label="Close">
                [CLOSE]
              </button>
            </div>
          </header>
          <div className={`min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 ${footer ? '' : 'pb-[max(16px,env(safe-area-inset-bottom))]'}`}>
            {children}
          </div>
          {footer && (
            <footer className="shrink-0 border-t-[1.5px] border-line p-4 pb-[max(16px,env(safe-area-inset-bottom))]">{footer}</footer>
          )}
        </div>
      )}
    </dialog>
  )
}
