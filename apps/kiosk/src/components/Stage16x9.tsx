import { useEffect, useRef, useState, type ReactNode } from 'react'

export const STAGE_W = 1920
export const STAGE_H = 1080

/**
 * Scene 16/9 a l'echelle : tout l'ecran est dessine en 1920x1080 et mis a
 * l'echelle pour remplir la fenetre (bandes noires si le ratio differe).
 * Les maquettes se transposent donc au pixel pres, quelle que soit la borne.
 */
export function Stage16x9({ children }: { children: ReactNode }) {
  const [scale, setScale] = useState(() => fit())

  const viewport = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onResize = () => setScale(fit())
    window.addEventListener('resize', onResize)
    // Certains changements de fenetre (emulation, plein ecran) n'emettent pas
    // toujours `resize` : on observe aussi le conteneur lui-meme.
    const observer = new ResizeObserver(onResize)
    if (viewport.current) observer.observe(viewport.current)
    return () => {
      window.removeEventListener('resize', onResize)
      observer.disconnect()
    }
  }, [])

  return (
    <div className="stage-viewport" ref={viewport}>
      <div
        className="stage"
        style={{
          width: STAGE_W,
          height: STAGE_H,
          transform: `translate(-50%, -50%) scale(${scale})`,
        }}
      >
        {children}
      </div>
    </div>
  )
}

function fit() {
  return Math.min(window.innerWidth / STAGE_W, window.innerHeight / STAGE_H)
}
