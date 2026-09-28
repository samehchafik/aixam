import { useEffect, useRef, useState, type ReactNode } from 'react'

export const STAGE_W = 1920
export const STAGE_H = 1080

/** Un fond d'ecran, dessine dans la scene : il suit tout ce qui s'y pose. */
export function Fond({ src }: { src: string }) {
  return <img className="fond" src={src} alt="" draggable={false} />
}

/**
 * Scene 16/9 a l'echelle : tout l'ecran est dessine en 1920x1080 puis mis a
 * l'echelle de la fenetre. Les maquettes se transposent donc au pixel pres,
 * quelle que soit la resolution de la borne.
 *
 * La scene COUVRE la fenetre : le fond occupe tout l'ecran, et sur une
 * fenetre qui n'est pas en 16/9 c'est une frange de la scene qui est rognee,
 * pas une marge qui apparait. Les ecrans du salon sont en 16/9 : rien n'y est
 * rogne.
 */
export function Stage16x9({ children }: { children: ReactNode }) {
  const [scale, setScale] = useState(() => fit() ?? 1)
  const viewport = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onResize = () => {
      const next = fit()
      if (next !== null) setScale(next)
    }

    onResize()
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

/**
 * Retourne `null` quand la fenetre se declare vide -- ce qui arrive le temps
 * d'une frame au demarrage ou en sortie de veille. Sans ce garde-fou on
 * figeait `scale(0)`, et la borne restait noire jusqu'au prochain
 * redimensionnement : sur un stand, personne ne redimensionne rien.
 */
function fit(): number | null {
  const w = window.innerWidth || document.documentElement.clientWidth
  const h = window.innerHeight || document.documentElement.clientHeight
  if (!w || !h) return null
  return Math.max(w / STAGE_W, h / STAGE_H)
}
