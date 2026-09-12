/**
 * Geometrie de la planche de bord EASY.
 *
 * Elle vient du gabarit du studio (`Gabarit_skin.svg`), conserve en points
 * dans `media/base/shape.json` : une polyligne fermee de plus de 250 sommets.
 * La planche n'est pas un rectangle arrondi -- ses bords ondulent legerement
 * et son encoche est une coupe franche. On ne la reconstruit donc pas a partir
 * de parametres, on la trace.
 *
 * `services/shape.py` cote serveur lit exactement les memes points.
 */
export type SkinShape = {
  width: number
  height: number
  /** Contour ferme, en unites du gabarit. */
  points: [number, number][]
  /** Creux central du bord bas, mesure a l'import : la place du panneau contextuel. */
  notch: { x: number; y: number; width: number; height: number }
}

type Ctx = Pick<CanvasRenderingContext2D, 'beginPath' | 'moveTo' | 'lineTo' | 'closePath'>

/**
 * Trace le contour de la planche dans un rectangle (0,0,w,h).
 *
 * Sans points -- un catalogue reste en arriere, par exemple -- on retombe sur
 * un simple rectangle. La planche perd sa silhouette, mais elle s'affiche :
 * sur un stand, mieux vaut une planche approximative qu'une planche absente.
 */
export function traceSkin(ctx: Ctx, shape: SkinShape, w: number, h: number): void {
  ctx.beginPath()
  const points = shape?.points
  if (!points?.length) {
    ctx.moveTo(0, 0)
    ctx.lineTo(w, 0)
    ctx.lineTo(w, h)
    ctx.lineTo(0, h)
    ctx.closePath()
    return
  }

  const sx = w / shape.width
  const sy = h / shape.height
  for (let i = 0; i < points.length; i++) {
    const [x, y] = points[i]
    if (i === 0) ctx.moveTo(x * sx, y * sy)
    else ctx.lineTo(x * sx, y * sy)
  }
  ctx.closePath()
}
