/**
 * Projection a quatre points, pour poser un skin sur la planche de bord
 * photographiee du diaporama.
 *
 * Le skin est plat, la planche est vue en perspective : une simple mise a
 * l'echelle ne suffit pas, il faut une homographie. Le navigateur sait en
 * appliquer une, via `matrix3d`, a condition de lui fournir les seize
 * coefficients -- c'est ce que produit ce module.
 *
 * Les quatre coins d'arrivee sont calcules a l'import (`import_assets.py`) en
 * faisant coincider le gabarit avec le masque livre par le studio. Ils vivent
 * dans `media/mockup/index.json` : si le studio refait la photo, l'import les
 * recalcule et rien ne change ici.
 */
export type Point = [number, number]

/**
 * Coefficients de l'homographie menant un rectangle (0,0,w,h) vers quatre
 * points. Resolution directe d'un systeme 8x8, par pivot de Gauss.
 */
function homographie(w: number, h: number, coins: Point[]): number[] {
  const source: Point[] = [
    [0, 0],
    [w, 0],
    [w, h],
    [0, h],
  ]
  const A: number[][] = []
  const B: number[] = []
  for (let i = 0; i < 4; i++) {
    const [u, v] = source[i]
    const [x, y] = coins[i]
    A.push([u, v, 1, 0, 0, 0, -u * x, -v * x])
    B.push(x)
    A.push([0, 0, 0, u, v, 1, -u * y, -v * y])
    B.push(y)
  }
  for (let i = 0; i < 8; i++) {
    let pivot = i
    for (let r = i + 1; r < 8; r++) if (Math.abs(A[r][i]) > Math.abs(A[pivot][i])) pivot = r
    ;[A[i], A[pivot]] = [A[pivot], A[i]]
    ;[B[i], B[pivot]] = [B[pivot], B[i]]
    for (let r = 0; r < 8; r++) {
      if (r === i || A[r][i] === 0) continue
      const f = A[r][i] / A[i][i]
      for (let c = 0; c < 8; c++) A[r][c] -= f * A[i][c]
      B[r] -= f * B[i]
    }
  }
  return A.map((_, i) => B[i] / A[i][i])
}

/** Applique une homographie a un point. */
function applique(m: number[], [x, y]: Point): Point {
  const w = m[6] * x + m[7] * y + 1
  return [(m[0] * x + m[1] * y + m[2]) / w, (m[3] * x + m[4] * y + m[5]) / w]
}

/**
 * La valeur CSS `transform` qui pose une image sur la planche.
 *
 * `planche` est la taille du gabarit, `coins` son emplacement dans la photo,
 * et `marge` le liseret que le rendu serveur ajoute autour du skin. L'image
 * couvre donc un rectangle plus grand que la planche : on le projette avec la
 * meme homographie, plutot que de rogner l'image.
 *
 * A utiliser avec `transform-origin: 0 0` sur un element de la taille de
 * l'image.
 */
export function matriceSkin(
  planche: { width: number; height: number },
  coins: Point[],
  marge: number,
): string {
  const versPhoto = homographie(planche.width, planche.height, coins)
  const w = planche.width + marge * 2
  const h = planche.height + marge * 2
  const image: Point[] = (
    [
      [-marge, -marge],
      [planche.width + marge, -marge],
      [planche.width + marge, planche.height + marge],
      [-marge, planche.height + marge],
    ] as Point[]
  ).map((p) => applique(versPhoto, p))

  const m = homographie(w, h, image)
  // matrix3d est donne colonne par colonne.
  return `matrix3d(${m[0]}, ${m[3]}, 0, ${m[6]}, ${m[1]}, ${m[4]}, 0, ${m[7]}, 0, 0, 1, 0, ${m[2]}, ${m[5]}, 0, 1)`
}
