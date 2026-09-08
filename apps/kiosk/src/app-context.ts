import { createContext, useContext } from 'react'
import type { ApiClient } from './api/client'
import type { ScreenBus } from './bus/screens'
import type { KioskConfig } from './runtime'

export type AppContextValue = {
  config: KioskConfig
  api: ApiClient
  bus: ScreenBus
  settings: {
    verification_bypass: boolean
    idle_timeout_seconds: number
    attract_interval_seconds: number
  }
}

export const AppContext = createContext<AppContextValue | null>(null)

export function useApp(): AppContextValue {
  const value = useContext(AppContext)
  if (!value) throw new Error('AppContext manquant')
  return value
}
