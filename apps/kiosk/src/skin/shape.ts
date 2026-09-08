/**
 * Geometrie de la planche de bord EASY. Lue depuis `media/base/shape.json`
 * (via le bootstrap), partagee avec `services/shape.py` cote serveur.
 */
export type SkinShape = {
  width: number
  height: number
  cornerRadius: number
  notch: { width: number; height: number; radius: number }
}

type Ctx = Pick<CanvasRenderingContext2D, 'beginPath' | 'moveTo' | 'lineTo' | 'arcTo' | 'closePath'>

/**
 * Trace le contour de la planche dans un rectangle (0,0,w,h) : angles
 * arrondis, encoche centrale ouverte vers le bas. Sert au clip du canvas et
 * au trait blanc de la maquette.
 */
export function traceSkin(ctx: Ctx, shape: SkinShape, w: number, h: number): void {
  const s = w / shape.width
  const r = shape.cornerRadius * s
  const nw = shape.notch.width * s
  const nh = shape.notch.height * (h / shape.height)
  const nr = shape.notch.radius * s
  const nx1 = (w - nw) / 2
  const nx2 = (w + nw) / 2
  const ny = h - nh

  ctx.beginPath()
  ctx.moveTo(r, 0)
  ctx.lineTo(w - r, 0)
  ctx.arcTo(w, 0, w, r, r)
  ctx.lineTo(w, h - r)
  ctx.arcTo(w, h, w - r, h, r)
  ctx.lineTo(nx2, h)
  ctx.lineTo(nx2, ny + nr)
  ctx.arcTo(nx2, ny, nx2 - nr, ny, nr)
  ctx.lineTo(nx1 + nr, ny)
  ctx.arcTo(nx1, ny, nx1, ny + nr, nr)
  ctx.lineTo(nx1, h)
  ctx.lineTo(r, h)
  ctx.arcTo(0, h, 0, h - r, r)
  ctx.lineTo(0, r)
  ctx.arcTo(0, 0, r, 0, r)
  ctx.closePath()
}
