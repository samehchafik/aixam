import { useEffect, useRef, useState, type ReactNode } from 'react'
import { matriceSkin } from '../skin/projection'
import type { Mockup } from '../api/client'
import type { SkinShape } from '../skin/shape'

/** URL d'une image du mockup, avec l'empreinte qui dejoue les caches. */
export function urlMockup(mockup: Mockup, mediaBase: string, fichier: string): string {
  return `${mediaBase}/${fichier}${mockup.version ? `?v=${mockup.version}` : ''}`
}


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
  const url = (fichier: string) => urlMockup(mockup, mediaBase, fichier)
  const [mx, my] = mockup.maskOrigin

  // Le rendu serveur entoure la planche d'un liseret. Sa largeur se lit sur
  // l'image elle-meme : inutile de la transporter dans une configuration, qui
  // finirait par diverger du serveur. Un calque dessine en direct, lui, n'en a
  // pas.
  const [marge, setMarge] = useState<number | null>(src ? null : 0)

  // Garde en reserve le rappel d'echec sans le mettre dans les dependances :
  // c'est une fonction anonyme, recreee a chaque rendu, et l'effet repartirait
  // en boucle -- remettant la marge a zero, donc redemandant l'image.
  const signaler = useRef(onErreur)
  signaler.current = onErreur

  useEffect(() => {
    if (!src) {
      setMarge(0)
      return
    }
    setMarge(null)
    const img = new window.Image()
    img.src = src
    img.onload = () => setMarge((img.naturalWidth - shape.width) / 2)
    // Sans ceci, une image qui ne vient jamais laissait la marge indefiniment
    // indeterminee, et le skin n'etait jamais pose. On previent le diaporama,
    // qui passe a la creation suivante.
    img.onerror = () => signaler.current?.()
    return () => {
      img.onload = null
      img.onerror = null
    }
  }, [src, shape.width])

  const [x, y, w, h] = [0, 0, mockup.width, mockup.height]

  return (
    <div className="mockup" style={{ width: w, height: h, left: x, top: y }}>
      <img className="mockup-decor" src={url(mockup.decor)} alt="" draggable={false} />

      {/* La zone est TOUJOURS posee. Elle etait conditionnee a la marge, donc
          au chargement du skin : tant qu'il n'etait pas la -- le temps du
          reseau, ou pour toujours s'il manquait -- la planche du mockup restait
          nue et laissait paraitre, en public, sa plaque verte « Placer le
          design ici ». Le noir doit couvrir cette plaque du premier instant, et
          quoi qu'il arrive au skin. */}
      <div
        className="mockup-zone"
        style={{
          // Le masque est livre recadre : on le repose a sa place, a sa taille
          // de scene -- il est dessine en 4K.
          WebkitMaskImage: `url(${url(mockup.masque)})`,
          maskImage: `url(${url(mockup.masque)})`,
          WebkitMaskPosition: `${mx}px ${my}px`,
          maskPosition: `${mx}px ${my}px`,
          ...(mockup.maskSize && {
            WebkitMaskSize: `${mockup.maskSize[0]}px ${mockup.maskSize[1]}px`,
            maskSize: `${mockup.maskSize[0]}px ${mockup.maskSize[1]}px`,
          }),
        }}
      >
        {marge !== null && (src || children) && (
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

      <img className="mockup-ombrage" src={url(mockup.ombrage)} alt="" draggable={false} />
    </div>
  )
}
