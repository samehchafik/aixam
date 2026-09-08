import { useEffect, useMemo, useRef, useState } from 'react'
import Konva from 'konva'
import { Group, Image as KImage, Layer as KLayer, Rect, Shape, Stage, Transformer } from 'react-konva'
import type { KonvaEventObject } from 'konva/lib/Node'
import type { Catalog, Layer } from '../api/client'
import { traceSkin } from '../skin/shape'

function useImage(src: string | null) {
  const [image, setImage] = useState<HTMLImageElement | null>(null)
  useEffect(() => {
    if (!src) {
      setImage(null)
      return
    }
    const img = new window.Image()
    img.crossOrigin = 'anonymous'
    img.src = src
    img.onload = () => setImage(img)
    return () => {
      img.onload = null
    }
  }, [src])
  return image
}

type Props = {
  catalog: Catalog
  layers: Layer[]
  mediaBase: string
  /** Largeur de la planche, en pixels de scene. */
  skinWidth: number
  /** Marge autour de la planche ou l'on voit les calques qui depassent (attenues). */
  bleed?: number
  interactive?: boolean
  selectedIndex?: number | null
  onSelect?: (index: number | null) => void
  onChange?: (index: number, patch: Partial<Layer>) => void
}

/**
 * La planche de bord et ses calques. Meme schema que `renderer.py` : ce que
 * le visiteur voit ici est ce qu'il recoit par mail.
 *
 * Les calques sont dessines deux fois : attenues sur toute la scene, puis a
 * pleine opacite a l'interieur du masque -- c'est le rendu de la maquette
 * (on voit ou l'on pousse son fond, mais seule la planche compte).
 */
export function SkinCanvas({
  catalog,
  layers,
  mediaBase,
  skinWidth,
  bleed = 0,
  interactive = false,
  selectedIndex = null,
  onSelect,
  onChange,
}: Props) {
  const shape = catalog.shape
  const skinHeight = skinWidth * (shape.height / shape.width)
  const stageW = skinWidth + bleed * 2
  const stageH = skinHeight + bleed * 2

  const urls = useMemo(() => {
    const map = new Map<string, string>()
    for (const item of [...catalog.backgrounds, ...catalog.objects]) map.set(item.id, `${mediaBase}/${item.image}`)
    return map
  }, [catalog, mediaBase])

  const transformer = useRef<Konva.Transformer>(null)
  const nodes = useRef(new Map<number, Konva.Node>())
  const selectedRef = useRef<number | null>(selectedIndex)
  selectedRef.current = selectedIndex

  const syncTransformer = () => {
    const tr = transformer.current
    if (!tr) return
    const node = selectedRef.current === null ? null : nodes.current.get(selectedRef.current)
    tr.nodes(node ? [node] : [])
    tr.getLayer()?.batchDraw()
  }

  useEffect(syncTransformer, [selectedIndex, layers])

  const ordered = [...layers].map((layer, index) => ({ layer, index })).sort((a, b) => a.layer.z - b.layer.z)

  const clip = (ctx: Konva.Context) => traceSkin(ctx, shape, skinWidth, skinHeight)

  const onStagePointer = (e: KonvaEventObject<MouseEvent | TouchEvent>) => {
    if (!interactive) return
    if (e.target === e.target.getStage()) onSelect?.(null)
  }

  const gesture = useTwoFingerGesture({
    enabled: interactive,
    selectedIndex,
    skinWidth,
    skinHeight,
    getNode: (i) => nodes.current.get(i) ?? null,
    onChange,
  })

  const renderLayers = (ghost: boolean) =>
    ordered.map(({ layer, index }) => (
      <LayerNode
        key={`${ghost ? 'g' : 'm'}-${index}`}
        index={index}
        layer={layer}
        src={layer.assetId ? (urls.get(layer.assetId) ?? null) : null}
        skinWidth={skinWidth}
        skinHeight={skinHeight}
        interactive={interactive && !ghost}
        register={(node) => {
          if (ghost) return
          if (node) nodes.current.set(index, node)
          else nodes.current.delete(index)
          // L'image peut arriver apres la selection : on rattache le cadre ici aussi.
          syncTransformer()
        }}
        onSelect={() => onSelect?.(index)}
        onChange={(patch) => onChange?.(index, patch)}
      />
    ))

  return (
    <Stage
      width={stageW}
      height={stageH}
      onMouseDown={onStagePointer}
      onTouchStart={(e) => {
        gesture.onTouchStart(e)
        onStagePointer(e)
      }}
      onTouchMove={gesture.onTouchMove}
      onTouchEnd={gesture.onTouchEnd}
      style={{ touchAction: 'none' }}
    >
      <KLayer>
        {/* Calques qui depassent : visibles mais attenues. */}
        {bleed > 0 && (
          <Group x={bleed} y={bleed} opacity={0.32} listening={false}>
            {renderLayers(true)}
          </Group>
        )}

        {/* La planche : fond blanc, calques a pleine opacite, decoupes au masque. */}
        <Group x={bleed} y={bleed} clipFunc={clip}>
          {/* Planche vide : le degrade violet -> peche de la maquette. */}
          <Rect
            width={skinWidth}
            height={skinHeight}
            fillLinearGradientStartPoint={{ x: 0, y: 0 }}
            fillLinearGradientEndPoint={{ x: skinWidth, y: skinHeight }}
            fillLinearGradientColorStops={[0, '#7a5fb0', 0.45, '#b7a0c9', 1, '#f6c3ad']}
            listening={false}
          />
          {renderLayers(false)}
        </Group>

        {/* Contour blanc de la maquette. */}
        <Shape
          x={bleed}
          y={bleed}
          listening={false}
          sceneFunc={(ctx, node) => {
            traceSkin(ctx, shape, skinWidth, skinHeight)
            ctx.fillStrokeShape(node)
          }}
          stroke="#ffffff"
          strokeWidth={3}
        />

        {interactive && (
          <Transformer
            ref={transformer}
            rotateEnabled
            keepRatio
            enabledAnchors={['top-left', 'top-right', 'bottom-left', 'bottom-right']}
            anchorSize={22}
            anchorCornerRadius={11}
            anchorStroke="#4FC3F7"
            anchorFill="#4FC3F7"
            borderStroke="#4FC3F7"
            borderStrokeWidth={2}
            borderDash={[10, 8]}
            rotateAnchorOffset={36}
            boundBoxFunc={(oldBox, newBox) => (newBox.width < 30 ? oldBox : newBox)}
          />
        )}
      </KLayer>
    </Stage>
  )
}

type NodeProps = {
  index: number
  layer: Layer
  src: string | null
  skinWidth: number
  skinHeight: number
  interactive: boolean
  register: (node: Konva.Node | null) => void
  onSelect: () => void
  onChange: (patch: Partial<Layer>) => void
}

/** Echelle effective d'un calque : un fond sans echelle couvre la planche. */
export function effectiveScale(layer: Layer, image: HTMLImageElement | null, skinWidth: number, skinHeight: number) {
  if (layer.scale !== undefined) return layer.scale
  if (!image) return 1
  return Math.max(1, (image.width / image.height) * (skinHeight / skinWidth))
}

function LayerNode({ layer, src, skinWidth, skinHeight, interactive, register, onSelect, onChange }: NodeProps) {
  const image = useImage(src)

  if (layer.type === 'background' && layer.hex) {
    // Un aplat de couleur se selectionne (pour le supprimer) mais ne se
    // transforme pas : pas de cadre ni de poignees.
    return (
      <Rect
        width={skinWidth}
        height={skinHeight}
        fill={layer.hex}
        listening={interactive}
        onMouseDown={onSelect}
        onTouchStart={onSelect}
      />
    )
  }

  if (!image) return null

  const scale = effectiveScale(layer, image, skinWidth, skinHeight)
  const w = scale * skinWidth
  const h = (image.height / image.width) * w

  const commit = (node: Konva.Node, extra: Partial<Layer> = {}) =>
    onChange({ x: node.x() / skinWidth, y: node.y() / skinHeight, rotation: node.rotation(), ...extra })

  return (
    <Group
      ref={register}
      x={layer.x * skinWidth}
      y={layer.y * skinHeight}
      rotation={layer.rotation}
      opacity={layer.opacity}
      draggable={interactive}
      listening={interactive}
      onMouseDown={onSelect}
      onTouchStart={onSelect}
      onDragEnd={(e) => commit(e.target)}
      onTransformEnd={(e) => {
        const node = e.target
        const next = scale * node.scaleX()
        node.scaleX(1)
        node.scaleY(1)
        commit(node, { scale: next })
      }}
    >
      <KImage image={image} width={w} height={h} offsetX={w / 2} offsetY={h / 2} />
    </Group>
  )
}

/**
 * Pincer pour zoomer, tourner, deplacer le calque selectionne. Le glisser a un
 * doigt reste gere par Konva ; a deux doigts on lui coupe la main.
 */
function useTwoFingerGesture(opts: {
  enabled: boolean
  selectedIndex: number | null
  skinWidth: number
  skinHeight: number
  getNode: (index: number) => Konva.Node | null
  onChange?: (index: number, patch: Partial<Layer>) => void
}) {
  const start = useRef<{
    dist: number
    angle: number
    cx: number
    cy: number
    x: number
    y: number
    scale: number
    rotation: number
  } | null>(null)

  const touchesOf = (e: KonvaEventObject<TouchEvent>) => {
    const t = e.evt.touches
    if (t.length < 2) return null
    const [a, b] = [t[0], t[1]]
    const dx = b.clientX - a.clientX
    const dy = b.clientY - a.clientY
    return {
      dist: Math.hypot(dx, dy),
      angle: (Math.atan2(dy, dx) * 180) / Math.PI,
      cx: (a.clientX + b.clientX) / 2,
      cy: (a.clientY + b.clientY) / 2,
    }
  }

  const onTouchStart = (e: KonvaEventObject<TouchEvent>) => {
    if (!opts.enabled || opts.selectedIndex === null) return
    const t = touchesOf(e)
    if (!t) return
    const node = opts.getNode(opts.selectedIndex)
    if (!node) return
    if (node.isDragging()) node.stopDrag()
    // Echelle de reference lue sur l'image rendue, pas sur layer.scale qui est
    // absent pour un fond en mode "cover".
    const child = node instanceof Konva.Group ? node.getChildren()[0] : node
    start.current = {
      ...t,
      x: node.x(),
      y: node.y(),
      scale: (child?.width() || node.width() || opts.skinWidth) / opts.skinWidth,
      rotation: node.rotation(),
    }
  }

  const onTouchMove = (e: KonvaEventObject<TouchEvent>) => {
    const s = start.current
    if (!s || opts.selectedIndex === null) return
    const t = touchesOf(e)
    if (!t) return
    e.evt.preventDefault()
    const node = opts.getNode(opts.selectedIndex)
    if (!node) return
    const stageScale = node.getStage()?.getAbsoluteScale().x ?? 1
    const ratio = t.dist / s.dist
    node.scale({ x: ratio, y: ratio })
    node.rotation(s.rotation + (t.angle - s.angle))
    node.position({ x: s.x + (t.cx - s.cx) / stageScale, y: s.y + (t.cy - s.cy) / stageScale })
    node.getLayer()?.batchDraw()
  }

  const onTouchEnd = (e: KonvaEventObject<TouchEvent>) => {
    const s = start.current
    if (!s || opts.selectedIndex === null) return
    if (e.evt.touches.length >= 2) return
    start.current = null
    const node = opts.getNode(opts.selectedIndex)
    if (!node) return
    const ratio = node.scaleX()
    node.scale({ x: 1, y: 1 })
    opts.onChange?.(opts.selectedIndex, {
      x: node.x() / opts.skinWidth,
      y: node.y() / opts.skinHeight,
      rotation: node.rotation(),
      scale: Math.max(0.02, s.scale * ratio),
    })
  }

  return { onTouchStart, onTouchMove, onTouchEnd }
}
