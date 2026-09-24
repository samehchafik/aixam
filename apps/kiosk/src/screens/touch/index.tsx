import { useEffect, useRef, type ComponentType } from 'react'
import { useApp } from '../../app-context'
import { useSession, type Step } from '../../state/session'
import { LangSwitch } from '../../components/chrome/LangSwitch'
import { AttractStep } from './AttractStep'
import { RegisterStep } from './RegisterStep'
import { VerifyStep } from './VerifyStep'
import { EditorStep } from './EditorStep'
import { ReviewStep } from './ReviewStep'
import { DoneStep } from './DoneStep'

/** Un ecran par etape du parcours ; chacun pose son propre decor. */
const ECRANS: Record<Step, ComponentType> = {
  attract: AttractStep,
  register: RegisterStep,
  verify: VerifyStep,
  editor: EditorStep,
  review: ReviewStep,
  done: DoneStep,
}

/**
 * Ecran tactile. Remet la session a zero apres inactivite : sur un salon,
 * un visiteur sur trois part au milieu du parcours.
 */
export function TouchScreen() {
  const { bus, settings } = useApp()
  const { step, reset } = useSession()
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

  const Ecran = ECRANS[step]
  return (
    <div className="touch-root">
      <Ecran />
      <LangSwitch />
    </div>
  )
}
