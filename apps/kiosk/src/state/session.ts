import { create } from 'zustand'
import type { Catalog, Layer } from '../api/client'

/**
 * Le parcours, dans l'ordre des ecrans du studio : accueil (1), formulaire
 * (2), code (3), creation (4 a 6), validation (7), remerciement (8).
 */
export type Step = 'attract' | 'register' | 'verify' | 'editor' | 'review' | 'done'

/** Ce que le visiteur a saisi au formulaire, par champ. */
export type Inscription = Record<string, string>

/**
 * Hauteur d'un objet a sa pose, en fraction de la hauteur de la planche. Les
 * objets livres vont du carre (228x235) au tres allonge (1249x265) : leur
 * donner a tous la meme LARGEUR ferait deborder les carres bien au-dela de la
 * planche. On fixe donc leur hauteur, et la largeur suit leur format.
 */
const OBJECT_HEIGHT = 0.55
/**
 * Largeur maximale d'un objet, en fraction de la planche.
 *
 * Poser a hauteur constante suffit tant que les objets ont des proportions
 * voisines. Un objet cinq fois plus large que haut devenait alors enorme : sa
 * hauteur etait juste, son etendue non. L'encoche laisse deux couloirs
 * d'environ 40 % de la planche ; un cinquieme, c'est la moitie d'un couloir,
 * donc deux objets peuvent encore s'y poser cote a cote.
 */
const OBJECT_WIDTH = 0.2

type State = {
  step: Step
  sessionId: string
  visitorId: string | null
  firstName: string
  /**
   * Le formulaire tel que le visiteur l'a laisse. Garde ici plutot que dans
   * l'ecran : revenir du code au formulaire -- pour corriger une adresse --
   * ne doit pas tout faire retaper.
   */
  inscription: Inscription
  layers: Layer[]
  selectedIndex: number | null
  catalog: Catalog | null
  renderUrl: string | null

  setStep: (step: Step) => void
  startSession: () => void
  reset: () => void
  clearDesign: () => void
  setVisitor: (id: string, firstName: string) => void
  setInscription: (inscription: Inscription) => void
  setCatalog: (catalog: Catalog) => void
  setRenderUrl: (url: string | null) => void

  /** Fond : un seul a la fois, toujours en z=0 et en premiere position. */
  setBackground: (background: { assetId?: string; hex?: string }) => void
  addObject: (assetId: string) => void
  updateLayer: (index: number, patch: Partial<Layer>) => void
  removeLayer: (index: number) => void
  /** Remet position, echelle et rotation d'un calque a leurs valeurs initiales. */
  resetLayer: (index: number) => void
  select: (index: number | null) => void
}

const newSessionId = () =>
  `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`

/** Marge de part et d'autre de l'encoche, en fraction de la largeur. */
const NOTCH_MARGIN = 0.015
/**
 * Marge minimale entre un objet et le bord de la planche. Minimale seulement :
 * la marge reelle tient compte de la largeur de l'objet, sans quoi les plus
 * larges naissaient a cheval sur le bord et le masque les coupait net.
 */
const EDGE = 0.08
/** Tirages tentes avant de garder le moins encombre. */
const ESSAIS = 14

/**
 * Bande centrale interdite : le panneau « Supprime / Reinitialise » s'y pose et
 * masquerait l'objet qui vient d'apparaitre. Elle est deduite de l'encoche du
 * gabarit, pas fixee a la main -- si le studio redessine la planche, elle suit.
 */
function bandeInterdite(catalog: Catalog | null): [number, number] {
  const forme = catalog?.shape
  if (!forme?.notch) return [0.4, 0.6]
  const debut = forme.notch.x / forme.width - NOTCH_MARGIN
  const fin = (forme.notch.x + forme.notch.width) / forme.width + NOTCH_MARGIN
  return [debut, fin]
}

/**
 * Un tirage dans les deux couloirs que l'encoche laisse libres.
 *
 * Les couloirs se resserrent de la demi-largeur de l'objet : c'est son BORD
 * qui doit rester sur la planche, pas son centre. Un objet large tire a
 * `EDGE` du bord debordait de la moitie de sa largeur moins EDGE, et le
 * masque le tranchait -- on voyait un dessin coupe, sans comprendre pourquoi.
 *
 * Quand l'objet est si large qu'aucun couloir ne le contient, on le pose au
 * milieu du plus grand : deborder un peu des deux cotes vaut mieux que
 * deborder beaucoup d'un seul.
 */
function tirage([interditDebut, interditFin]: [number, number], demiLargeur = 0): number {
  const marge = Math.max(EDGE, demiLargeur)
  const gauche = Math.max(0, interditDebut - demiLargeur - marge)
  const droite = Math.max(0, 1 - marge - (interditFin + demiLargeur))

  if (gauche + droite <= 0) {
    const milieu = (debut: number, fin: number) => (debut + fin) / 2
    return interditDebut > 1 - interditFin
      ? milieu(0, interditDebut)
      : milieu(interditFin, 1)
  }

  const t = Math.random() * (gauche + droite)
  return t < gauche ? marge + t : interditFin + demiLargeur + (t - gauche)
}

/**
 * Abscisse de naissance d'un objet.
 *
 * Un tirage seul ne suffit pas : les objets livres vont jusqu'a un quart de la
 * planche de large, et deux d'entre eux tires dans le meme couloir se
 * recouvrent presque entierement -- on croit alors qu'ils apparaissent tous au
 * meme endroit. On tire donc plusieurs fois et on garde la position la plus
 * degagee, en tenant compte de la largeur de chacun. Des qu'un tirage ne
 * chevauche rien, on s'arrete : le hasard garde la main tant qu'il y a de la
 * place.
 */
function spawnX(
  catalog: Catalog | null,
  demiLargeur: number,
  poses: { x: number; demi: number }[],
): number {
  const bande = bandeInterdite(catalog)
  let meilleur = tirage(bande, demiLargeur)
  if (!poses.length) return meilleur

  let meilleurEcart = -Infinity
  for (let i = 0; i < ESSAIS; i++) {
    const candidat = i === 0 ? meilleur : tirage(bande, demiLargeur)
    const ecart = Math.min(
      ...poses.map((p) => Math.abs(candidat - p.x) - (demiLargeur + p.demi)),
    )
    if (ecart > meilleurEcart) {
      meilleurEcart = ecart
      meilleur = candidat
    }
    if (meilleurEcart > 0) break
  }
  return meilleur
}

/**
 * Echelle de pose, en fraction de la LARGEUR de planche.
 *
 * Deux bornes, la plus contraignante l'emporte : une hauteur de pose, qui
 * donne aux objets un poids visuel comparable, et une largeur maximale, qui
 * retient ceux que leurs proportions feraient deborder.
 */
function objectScale(catalog: Catalog | null, assetId: string | undefined): number {
  const item = catalog?.objects.find((o) => o.id === assetId)
  if (!catalog || !item || !item.height) return 0.12
  const format = item.width / item.height
  const planche = catalog.shape.height / catalog.shape.width
  return Math.min(OBJECT_HEIGHT * planche * format, OBJECT_WIDTH)
}

const objectDefaults = (
  x: number,
  scale: number,
): Pick<Layer, 'x' | 'y' | 'scale' | 'rotation' | 'opacity'> => ({
  x,
  y: 0.5,
  scale,
  rotation: 0,
  opacity: 1,
})

export const useSession = create<State>((set) => ({
  step: 'attract',
  sessionId: newSessionId(),
  visitorId: null,
  firstName: '',
  inscription: {},
  layers: [],
  selectedIndex: null,
  catalog: null,
  renderUrl: null,

  setStep: (step) => set({ step }),
  startSession: () => set({ step: 'register', sessionId: newSessionId() }),
  reset: () =>
    set({
      step: 'attract',
      sessionId: newSessionId(),
      visitorId: null,
      firstName: '',
      inscription: {},
      layers: [],
      selectedIndex: null,
      renderUrl: null,
    }),
  clearDesign: () => set({ layers: [], selectedIndex: null }),
  setVisitor: (visitorId, firstName) => set({ visitorId, firstName }),
  setInscription: (inscription) => set({ inscription }),
  setCatalog: (catalog) => set({ catalog }),
  setRenderUrl: (renderUrl) => set({ renderUrl }),

  setBackground: (background) =>
    set((s) => ({
      layers: [
        { type: 'background', ...background, x: 0.5, y: 0.5, rotation: 0, opacity: 1, z: 0 },
        ...s.layers.filter((l) => l.type !== 'background'),
      ],
      selectedIndex: 0,
    })),

  addObject: (assetId) =>
    set((s) => {
      const scale = objectScale(s.catalog, assetId)
      const poses = s.layers
        .filter((l) => l.type === 'object')
        .map((l) => ({ x: l.x, demi: (l.scale ?? 0.12) / 2 }))
      const x = spawnX(s.catalog, scale / 2, poses)
      return {
        layers: [
          ...s.layers,
          { type: 'object', assetId, spawnX: x, ...objectDefaults(x, scale), z: s.layers.length + 1 },
        ],
        selectedIndex: s.layers.length,
      }
    }),

  updateLayer: (index, patch) =>
    set((s) => ({
      layers: s.layers.map((layer, i) => (i === index ? { ...layer, ...patch } : layer)),
    })),

  removeLayer: (index) =>
    set((s) => ({ layers: s.layers.filter((_, i) => i !== index), selectedIndex: null })),

  resetLayer: (index) =>
    set((s) => ({
      layers: s.layers.map((layer, i) => {
        if (i !== index) return layer
        if (layer.type === 'background') {
          const { scale: _cover, ...rest } = layer
          return { ...rest, x: 0.5, y: 0.5, rotation: 0 }
        }
        // Retour a l'endroit ou l'objet est apparu, pas a un nouveau tirage :
        // « reinitialiser » ne doit pas le faire sauter de cote.
        return { ...layer, ...objectDefaults(layer.spawnX ?? layer.x, objectScale(s.catalog, layer.assetId)) }
      }),
    })),

  select: (selectedIndex) => set({ selectedIndex }),
}))
