import { useEffect, useState } from 'react'
import { matriceSkin } from '../skin/projection'
import type { Mockup } from '../api/client'
import type { SkinShape } from '../skin/shape'

type Props = {
  mockup: Mockup
  shape: SkinShape
  mediaBase: string
  /** URL du JPEG rendu par le serveur. */
  src: string
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
export function SkinMockup({ mockup, shape, mediaBase, src }: Props) {
  const [marge, setMarge] = useState<number | null>(null)

  // Le rendu serveur entoure la planche d'un liseret. Sa largeur se lit sur
  // l'image elle-meme : inutile de la transporter dans une configuration, qui
  // finirait par diverger du serveur.
  useEffect(() => {
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
      <img className="mockup-decor" src={`${mediaBase}/${mockup.decor}`} alt="" />

      {marge !== null && (
        <div
          className="mockup-zone"
          style={{
            // Le masque est livre recadre : on le repose a sa place.
            WebkitMaskImage: `url(${mediaBase}/${mockup.masque})`,
            maskImage: `url(${mediaBase}/${mockup.masque})`,
            WebkitMaskPosition: `${mockup.maskOrigin[0]}px ${mockup.maskOrigin[1]}px`,
            maskPosition: `${mockup.maskOrigin[0]}px ${mockup.maskOrigin[1]}px`,
          }}
        >
          <img
            src={src}
            alt=""
            style={{
              width: shape.width + marge * 2,
              height: shape.height + marge * 2,
              transform: matriceSkin(shape, mockup.corners, marge),
            }}
          />
        </div>
      )}

      <img className="mockup-ombrage" src={`${mediaBase}/${mockup.ombrage}`} alt="" />
    </div>
  )
}
