import { useEffect, useMemo, useState } from 'react'
import { MantineProvider, Text, Title } from '@mantine/core'
import { ApiClient } from './api/client'
import { ScreenBus } from './bus/screens'
import { AppContext, type AppContextValue } from './app-context'
import { Stage16x9 } from './components/Stage16x9'
import { I18nProvider, useI18n } from './i18n'
import { getRuntime, type KioskConfig, type ScreenRole } from './runtime'
import { useSession } from './state/session'
import { TouchScreen } from './screens/touch'
import { DisplayScreen } from './screens/display'
import { theme } from './theme'

/** Le role vient du hash : #/display sur le grand ecran, rien sur le tactile. */
function resolveRole(): ScreenRole {
  return window.location.hash.includes('display') ? 'display' : 'touch'
}

export default function App() {
  const role = useMemo(resolveRole, [])
  const [ctx, setCtx] = useState<AppContextValue | null>(null)
  const [error, setError] = useState<string | null>(null)
  const setCatalog = useSession((s) => s.setCatalog)

  useEffect(() => {
    let bus: ScreenBus | null = null

    ;(async () => {
      try {
        const runtime = await getRuntime()
        const config: KioskConfig = await runtime.loadConfig()
        await runtime.keepAwake()

        const api = new ApiClient(config)
        const boot = await api.bootstrap()
        setCatalog(boot.catalog)

        bus = new ScreenBus(config, role)
        bus.connect()

        // Seul l'ecran tactile pilote l'ouverture du second ecran.
        if (role === 'touch') await runtime.openDisplayWindow(config)

        setCtx({ config, api, bus, settings: boot.settings })
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Erreur de demarrage')
      }
    })()

    return () => bus?.close()
  }, [role, setCatalog])

  return (
    <MantineProvider theme={theme} forceColorScheme="dark">
      <I18nProvider initial={ctx?.config.locale ?? 'fr'}>
        <Stage16x9>
          {error ? (
            <BootError message={error} />
          ) : !ctx ? (
            <Booting />
          ) : (
            <AppContext.Provider value={ctx}>
              {role === 'display' ? <DisplayScreen /> : <TouchScreen />}
            </AppContext.Provider>
          )}
        </Stage16x9>
      </I18nProvider>
    </MantineProvider>
  )
}

function Booting() {
  const { t } = useI18n()
  return <div className="boot"><Text size="xl">{t('boot.loading')}</Text></div>
}

function BootError({ message }: { message: string }) {
  const { t } = useI18n()
  return (
    <div className="boot">
      <Title order={1}>{t('boot.unavailable')}</Title>
      <Text size="lg">{message}</Text>
      <Text c="dimmed" size="sm">{t('boot.hint')}</Text>
    </div>
  )
}
