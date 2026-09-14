import { useEffect, useState, type ReactNode } from 'react'
import { matriceSkin } from '../skin/projection'
import type { Mockup } from '../api/client'
import type { SkinShape } from '../skin/shape'

type Props = {
  mockup: Mockup
  shape: SkinShape
  mediaBase: string
  /** URL du JPEG rendu par le serveur. */
  src?: string
  /**
   * Skin a poser quand il n'y a pas de rendu : un calque dessine en direct,
   * aux dimensions du gabarit. Sert au debut du salon, quand aucune creation
   * n'a encore ete approuvee -- l'ecran montre alors la voiture plutot qu'un
   * repli qui ressemble a une panne.
   */
  children?: ReactNode
  /** Appele quand le rendu ne charge pas : au diaporama de passer au suivant. */
  onErreur?: () => void
}

/**
 * Une creation posee sur la planche de bord, pour le diaporama.
 *
 * Trois couches livrees par le studio : le decor photographie, le masque de la
 * zone, l'ombrage. Entre les deux premieres vient le skin, redresse par une
 * projection a quatre points -- la planche est vue de biais, une mise a
 * l'echelle ne suffirait pas.
 *
 * Le masque sert de decoupe : il retient ce qui deborde de la planche, y
 * compris ce que le volant et le montant de pare-brise cachent. L'ombrage
 * repose par-dessus, pour que le skin prenne la lumiere de la photo.
 */
export function SkinMockup({ mockup, shape, mediaBase, src, children, onErreur }: Props) {
  // Meme raison que pour le catalogue : ces trois images changent sous le meme
  // nom quand le studio livre un nouveau mockup, et un cache les garderait.
  const v = mockup.version ? `?v=${mockup.version}` : ''

  // Le rendu serveur entoure la planche d'un liseret. Sa largeur se lit sur
  // l'image elle-meme : inutile de la transporter dans une configuration, qui
  // finirait par diverger du serveur. Un calque dessine en direct, lui, n'en a
  // pas.
  const [marge, setMarge] = useState<number | null>(src ? null : 0)

  useEffect(() => {
    if (!src) {
      setMarge(0)
      return
    }
    setMarge(null)
    const img = new window.Image()
    img.src = src
    img.onload = () => setMarge((img.naturalWidth - shape.width) / 2)
    return () => {
      img.onload = null
    }
  }, [src, shape.width])

  const [x, y, w, h] = [0, 0, mockup.width, mockup.height]

  return (
    <div className="mockup" style={{ width: w, height: h, left: x, top: y }}>
      <img className="mockup-decor" src={`${mediaBase}/${mockup.decor}${v}`} alt="" />

      {marge !== null && (
        <div
          className="mockup-zone"
          style={{
            // Le masque est livre recadre : on le repose a sa place.
            WebkitMaskImage: `url(${mediaBase}/${mockup.masque}${v})`,
            maskImage: `url(${mediaBase}/${mockup.masque}${v})`,
            WebkitMaskPosition: `${mockup.maskOrigin[0]}px ${mockup.maskOrigin[1]}px`,
            maskPosition: `${mockup.maskOrigin[0]}px ${mockup.maskOrigin[1]}px`,
          }}
        >
          {(src || children) && (
            <div
              className="mockup-skin"
              style={{
                width: shape.width + marge * 2,
                height: shape.height + marge * 2,
                transform: matriceSkin(shape, mockup.corners, marge),
              }}
            >
              {src ? <img src={src} alt="" onError={onErreur} /> : children}
            </div>
          )}
        </div>
      )}

      <img className="mockup-ombrage" src={`${mediaBase}/${mockup.ombrage}${v}`} alt="" />
    </div>
  )
}
