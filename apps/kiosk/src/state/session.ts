import { create } from 'zustand'
import type { Catalog, Layer } from '../api/client'

export type Step = 'attract' | 'register' | 'verify' | 'editor' | 'done'

/**
 * Hauteur d'un objet a sa pose, en fraction de la hauteur de la planche. Les
 * objets livres vont du carre (228x235) au tres allonge (1249x265) : leur
 * donner a tous la meme LARGEUR ferait deborder les carres bien au-dela de la
 * planche. On fixe donc leur hauteur, et la largeur suit leur format.
 */
const OBJECT_HEIGHT = 0.55

type State = {
  step: Step
  sessionId: string
  visitorId: string | null
  firstName: string
  layers: Layer[]
  selectedIndex: number | null
  catalog: Catalog | null
  renderUrl: string | null

  setStep: (step: Step) => void
  startSession: () => void
  reset: () => void
  clearDesign: () => void
  setVisitor: (id: string, firstName: string) => void
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
/** Un objet ne nait pas a cheval sur un bord de la planche. */
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

/** Un tirage dans les deux couloirs que l'encoche laisse libres. */
function tirage([interditDebut, interditFin]: [number, number]): number {
  const gauche = Math.max(0, interditDebut - EDGE)
  const droite = Math.max(0, 1 - EDGE - interditFin)
  const t = Math.random() * (gauche + droite)
  return t < gauche ? EDGE + t : interditFin + (t - gauche)
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
  let meilleur = tirage(bande)
  if (!poses.length) return meilleur

  let meilleurEcart = -Infinity
  for (let i = 0; i < ESSAIS; i++) {
    const candidat = i === 0 ? meilleur : tirage(bande)
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

/** Echelle de pose (fraction de la LARGEUR de planche) pour une hauteur donnee. */
function objectScale(catalog: Catalog | null, assetId: string | undefined): number {
  const item = catalog?.objects.find((o) => o.id === assetId)
  if (!catalog || !item || !item.height) return 0.12
  const format = item.width / item.height
  const planche = catalog.shape.height / catalog.shape.width
  return OBJECT_HEIGHT * planche * format
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
      layers: [],
      selectedIndex: null,
      renderUrl: null,
    }),
  clearDesign: () => set({ layers: [], selectedIndex: null }),
  setVisitor: (visitorId, firstName) => set({ visitorId, firstName }),
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
