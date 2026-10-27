import type { Dispatch } from 'react'
import { api, ApiError } from './api'
import type { Action } from './store'

/* Job actions shared by the queue and history. Failures surface as a toast. */
export function jobActions(dispatch: Dispatch<Action>) {
  const run = async (fn: () => Promise<void>) => {
    try {
      await fn()
    } catch (e) {
      dispatch({ type: 'toast', text: e instanceof ApiError ? e.message : 'Something went wrong.' })
    }
  }
  return {
    cancel: (id: string) => run(async () => dispatch({ type: 'upsert', jobs: [await api.cancel(id)] })),
    retry: (id: string) => run(async () => dispatch({ type: 'upsert', jobs: [await api.retry(id)] })),
    remove: (id: string) =>
      run(async () => {
        await api.remove(id)
        dispatch({ type: 'remove', id })
      }),
  }
}
