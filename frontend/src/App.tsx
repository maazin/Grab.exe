import { useEffect, useState } from 'react'
import { IconButton, SettingsIcon } from './components/ui'
import { Toasts } from './components/Toasts'
import { GrabCard } from './screens/GrabCard'
import { History } from './screens/History'
import { Queue } from './screens/Queue'
import { Settings } from './screens/Settings'
import { useJobs } from './store'

type Route = 'home' | 'history'

const routeFromHash = (): Route => (location.hash === '#/history' ? 'history' : 'home')

export default function App() {
  const { state, dispatch } = useJobs()
  const [route, setRoute] = useState<Route>(routeFromHash)
  const [settingsOpen, setSettingsOpen] = useState(false)

  useEffect(() => {
    const on = () => setRoute(routeFromHash())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])

  useEffect(() => {
    document.title = route === 'history' ? 'History · Grab' : 'Grab'
  }, [route])

  return (
    <div className="mx-auto max-w-[600px] px-4 pb-28 pt-[max(12px,env(safe-area-inset-top))]">
      <header className="flex h-14 items-center justify-between">
        <a href="#/" className="font-pixel text-[20px] leading-none tracking-[0.04em]" aria-label="Grab, home">
          GRAB
        </a>
        <nav className="flex items-center gap-1">
          <a
            href={route === 'history' ? '#/' : '#/history'}
            aria-current={route === 'history' ? 'page' : undefined}
            className="inline-flex min-h-11 items-center rounded-[4px] px-3 font-medium hover:bg-ink/5 aria-[current=page]:underline aria-[current=page]:decoration-accent aria-[current=page]:decoration-2 aria-[current=page]:underline-offset-4"
          >
            History
          </a>
          <IconButton label="Settings" onClick={() => setSettingsOpen(true)}>
            <SettingsIcon />
          </IconButton>
        </nav>
      </header>

      <main className="space-y-4">
        {route === 'home' ? (
          <>
            <GrabCard dispatch={dispatch} />
            <Queue jobs={state.jobs} dispatch={dispatch} />
          </>
        ) : (
          <History jobs={state.jobs} dispatch={dispatch} />
        )}
      </main>

      <Settings open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <Toasts toasts={state.toasts} dispatch={dispatch} />
    </div>
  )
}
