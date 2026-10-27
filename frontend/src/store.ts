import { useEffect, useReducer } from 'react'
import { api, type Job } from './api'

export interface Toast {
  key: number
  text: string
  jobId?: string
}

export interface State {
  jobs: Record<string, Job>
  toasts: Toast[]
}

export type Action =
  | { type: 'upsert'; jobs: Job[] }
  | { type: 'remove'; id: string }
  | { type: 'toast'; text: string; jobId?: string }
  | { type: 'dismiss'; key: number }

let toastKey = 0

export function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'upsert': {
      const jobs = { ...state.jobs }
      const toasts = [...state.toasts]
      for (const job of action.jobs) {
        const prev = jobs[job.id]
        // Events can arrive out of order with fetch results; never step back from a finished state.
        if (prev && prev.status !== job.status && isFinal(prev.status) && !isFinal(job.status)) continue
        if (prev && prev.status !== 'done' && job.status === 'done') {
          toasts.push({ key: ++toastKey, text: job.title, jobId: job.id })
        }
        jobs[job.id] = job
      }
      return { jobs, toasts: toasts.slice(-3) }
    }
    case 'remove': {
      const jobs = { ...state.jobs }
      delete jobs[action.id]
      return { ...state, jobs }
    }
    case 'toast':
      return { ...state, toasts: [...state.toasts, { key: ++toastKey, text: action.text, jobId: action.jobId }].slice(-3) }
    case 'dismiss':
      return { ...state, toasts: state.toasts.filter((t) => t.key !== action.key) }
  }
}

const isFinal = (s: Job['status']) => s === 'done' || s === 'failed' || s === 'canceled' || s === 'expired'

export function useJobs() {
  const [state, dispatch] = useReducer(reducer, { jobs: {}, toasts: [] })
  useEffect(() => {
    let closed = false
    const sync = () =>
      api
        .jobs()
        .then(({ jobs }) => !closed && dispatch({ type: 'upsert', jobs }))
        .catch(() => {})

    const es = new EventSource('/api/events')
    // EventSource reconnects on its own; every (re)connect resyncs in case events were missed.
    es.onopen = sync
    es.addEventListener('job', (e) => {
      try {
        dispatch({ type: 'upsert', jobs: [JSON.parse((e as MessageEvent).data) as Job] })
      } catch {
        // ignore a malformed event
      }
    })
    sync()
    return () => {
      closed = true
      es.close()
    }
  }, [])

  return { state, dispatch }
}
