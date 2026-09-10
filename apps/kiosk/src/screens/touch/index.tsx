import { useEffect, useRef } from 'react'
import { Text, Title } from '@mantine/core'
import { useApp } from '../../app-context'
import { useI18n } from '../../i18n'
import { useSession } from '../../state/session'
import { Ribbon } from '../../components/chrome/Ribbon'
import { BrandMark } from '../../components/chrome/BrandMark'
import { LangSwitch } from '../../components/chrome/LangSwitch'
import { RegisterStep } from './RegisterStep'
import { VerifyStep } from './VerifyStep'
import { EditorStep } from './EditorStep'
import { DoneStep } from './DoneStep'

/**
 * Ecran tactile. Remet la session a zero apres inactivite : sur un salon,
 * un visiteur sur trois part au milieu du parcours.
 */
export function TouchScreen() {
  const { bus, settings } = useApp()
  const { t } = useI18n()
  const { step, startSession, reset } = useSession()
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    const schedule = () => {
      window.clearTimeout(timer.current)
      if (step === 'attract') return
      timer.current = window.setTimeout(() => {
        reset()
        bus.send({ type: 'idle' })
      }, settings.idle_timeout_seconds * 1000)
    }

    schedule()
    const events = ['pointerdown', 'keydown'] as const
    events.forEach((name) => window.addEventListener(name, schedule))
    return () => {
      window.clearTimeout(timer.current)
      events.forEach((name) => window.removeEventListener(name, schedule))
    }
  }, [step, settings.idle_timeout_seconds, reset, bus])

  useEffect(() => {
    if (step === 'attract') bus.send({ type: 'idle' })
  }, [step, bus])

  return (
    <div className="touch-root">
      {/* Sur l'editeur, le bandeau est rendu ENTRE les deux canvas de la
          planche (au-dessus du fond, sous les objets) : c'est SkinCanvas qui
          le place. Ailleurs, il n'a rien a traverser. */}
      {step !== 'editor' && <Ribbon />}
      <BrandMark />
      <LangSwitch />

      {step === 'attract' && (
        <button type="button" className="attract" onClick={startSession}>
          <Title order={1} className="attract-title">{t('attract.title')}</Title>
          <Text size="xl" c="dimmed">{t('attract.cta')}</Text>
        </button>
      )}
      {step === 'register' && <RegisterStep />}
      {step === 'verify' && <VerifyStep />}
      {step === 'editor' && <EditorStep />}
      {step === 'done' && <DoneStep />}
    </div>
  )
}
