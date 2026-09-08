import { create } from 'zustand'
import type { Catalog, Layer } from '../api/client'

export type Step = 'attract' | 'register' | 'verify' | 'editor' | 'done'

export const OBJECT_DEFAULT_SCALE = 0.12

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

// Un objet arrive a droite de l'encoche (au centre il serait cache par le
// panneau contextuel), comme sur la maquette.
const objectDefaults = (): Pick<Layer, 'x' | 'y' | 'scale' | 'rotation' | 'opacity'> => ({
  x: 0.74,
  y: 0.5,
  scale: OBJECT_DEFAULT_SCALE,
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
    set((s) => ({
      layers: [...s.layers, { type: 'object', assetId, ...objectDefaults(), z: s.layers.length + 1 }],
      selectedIndex: s.layers.length,
    })),

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
        return { ...layer, ...objectDefaults() }
      }),
    })),

  select: (selectedIndex) => set({ selectedIndex }),
}))
