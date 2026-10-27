import { useEffect, type Dispatch } from 'react'
import { fileUrl } from '../api'
import type { Action, Toast } from '../store'
import { buttonClass } from './ui'

const SHOW_MS = 6000

function ToastItem({ toast, dispatch }: { toast: Toast; dispatch: Dispatch<Action> }) {
  useEffect(() => {
    const t = setTimeout(() => dispatch({ type: 'dismiss', key: toast.key }), SHOW_MS)
    return () => clearTimeout(t)
  }, [toast.key, dispatch])

  return (
    <div className="anim-toast frame shadow-hard flex items-center gap-3 bg-surface py-1.5 pl-3 pr-1.5">
      <p className="min-w-0 flex-1 truncate">
        {toast.jobId ? (
          <>
            <span className="label mr-2">Done ·</span>
            {toast.text}
          </>
        ) : (
          toast.text
        )}
      </p>
      {toast.jobId && (
        <a href={fileUrl(toast.jobId)} download className={buttonClass('primary', 'sm')} onClick={() => dispatch({ type: 'dismiss', key: toast.key })}>
          Save
        </a>
      )}
    </div>
  )
}

export function Toasts({ toasts, dispatch }: { toasts: Toast[]; dispatch: Dispatch<Action> }) {
  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-0 z-30 mx-auto flex max-w-[600px] flex-col gap-2 px-4 pb-[max(16px,env(safe-area-inset-bottom))] [&>*]:pointer-events-auto"
    >
      {toasts.map((t) => (
        <ToastItem key={t.key} toast={t} dispatch={dispatch} />
      ))}
    </div>
  )
}
