import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import Konva from 'konva'
import { Group, Image as KImage, Layer as KLayer, Line, Rect, Shape, Stage, Transformer } from 'react-konva'
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

export type Bleed = { x: number; top: number; bottom: number }

const SKY = '#4FC3F7'

type Props = {
  catalog: Catalog
  layers: Layer[]
  mediaBase: string
  /** Largeur de la planche, en pixels de scene. */
  skinWidth: number
  /**
   * Marge autour de la planche ou l'on voit les calques qui depassent
   * (attenues). Un nombre = la meme marge partout ; la maquette en veut une
   * plus grande en bas, ou vient se poser le texte d'aide.
   */
  bleed?: number | Bleed
  /**
   * Taille du canvas et position de la planche dedans. Sans ces deux-la, le
   * canvas se limite a la planche plus sa marge. L'editeur les donne pour que
   * le canvas couvre toute la scene 16/9 : un objet peut alors etre pousse
   * n'importe ou -- au-dessus du bandeau, hors de la zone de debordement --
   * sans etre coupe par le bord du canvas.
   */
  stage?: { width: number; height: number }
  origin?: { x: number; y: number }
  /**
   * Glisse entre les deux canvas : au-dessus du fond, sous les objets. C'est
   * la place du bandeau du haut dans la maquette.
   */
  middle?: ReactNode
  interactive?: boolean
  selectedIndex?: number | null
  onSelect?: (index: number | null) => void
  onChange?: (index: number, patch: Partial<Layer>) => void
}

/**
 * La planche de bord et ses calques. Meme schema que `renderer.py` : ce que
 * le visiteur voit ici est ce qu'il recoit par mail.
 *
 * Le rendu est coupe en DEUX canvas empiles, pour qu'un element de decor DOM
 * puisse se glisser entre eux :
 *
 *   canvas du fond   la planche, son fond, son contour     (rien n'ecoute)
 *   `middle`         le bandeau du haut
 *   canvas du dessus les objets, le cadre, les poignees    (tout ecoute)
 *
 * Le fond n'etant plus cliquable la ou il est dessine, sa manipulation passe
 * par deux mandataires dans le canvas du dessus : une forme a la silhouette de
 * la planche pour le selectionner et le deplacer, un rectangle pour porter les
 * poignees. Les deux pilotent le vrai noeud, reste en bas.
 *
 * Chaque calque est dessine deux fois : attenue hors de la planche, a pleine
 * opacite dedans. Le fond attenue reste confine a la zone de debordement, les
 * objets vont ou on les pousse.
 */
export function SkinCanvas({
  catalog,
  layers,
  mediaBase,
  skinWidth,
  bleed = 0,
  stage,
  origin: originProp,
  middle,
  interactive = false,
  selectedIndex = null,
  onSelect,
  onChange,
}: Props) {
  const shape = catalog.shape
  const skinHeight = skinWidth * (shape.height / shape.width)
  const marge: Bleed = typeof bleed === 'number' ? { x: bleed, top: bleed, bottom: bleed } : bleed
  const stageW = stage?.width ?? skinWidth + marge.x * 2
  const stageH = stage?.height ?? skinHeight + marge.top + marge.bottom
  // Coin haut-gauche de la planche dans le canvas.
  const origin = originProp ?? { x: marge.x, y: marge.top }
  // Zone de debordement : la planche plus sa marge. C'est le cadre du fond et
  // la limite du fond attenue ; les objets, eux, peuvent en sortir.
  const ghost = {
    x: origin.x - marge.x,
    y: origin.y - marge.top,
    w: skinWidth + marge.x * 2,
    h: skinHeight + marge.top + marge.bottom,
  }
  const hasBleed = marge.x > 0 || marge.top > 0 || marge.bottom > 0
  const selectedLayer = selectedIndex === null ? null : (layers[selectedIndex] ?? null)

  const bgIndex = layers.findIndex((l) => l.type === 'background')
  const bgLayer = bgIndex < 0 ? null : layers[bgIndex]

  const urls = useMemo(() => {
    const map = new Map<string, string>()
    for (const item of [...catalog.backgrounds, ...catalog.objects]) map.set(item.id, `${mediaBase}/${item.image}`)
    return map
  }, [catalog, mediaBase])

  const transformer = useRef<Konva.Transformer>(null)
  const nodes = useRef(new Map<number, Konva.Node>())
  const selectedRef = useRef<number | null>(selectedIndex)
  selectedRef.current = selectedIndex
  const layersRef = useRef(layers)
  layersRef.current = layers

  // Le cadre de selection d'un objet vit HORS du groupe decoupe par le masque
  // -- sur la maquette il deborde de la planche. Il ne peut donc pas etre un
  // enfant de l'objet ; on le fait suivre a la main, a chaque mouvement.
  const frameGroup = useRef<Konva.Group>(null)
  const frameRect = useRef<Konva.Rect>(null)
  const frameLines = useRef<(Konva.Line | null)[]>([])

  // Mandataires du fond, dans le canvas du dessus. `bgHit` a la silhouette de
  // la planche : il capte le clic et le glisser. `proxy` a la taille du cadre :
  // il porte les poignees, dont les coins du fond -- bien plus grand que la
  // scene -- tomberaient hors champ.
  const bgHit = useRef<Konva.Rect>(null)
  const bgDrag = useRef<{ hit: { x: number; y: number }; node: { x: number; y: number } } | null>(null)
  const proxy = useRef<Konva.Rect>(null)
  const proxyStart = useRef<{ sx: number; rot: number } | null>(null)
  const FRAME_INSET = 4

  const selectedNode = () => (selectedRef.current === null ? undefined : nodes.current.get(selectedRef.current))
  const selectedKind = (): 'object' | 'image-bg' | 'hex-bg' | null => {
    const idx = selectedRef.current
    const layer = idx === null ? undefined : layersRef.current[idx]
    if (!layer) return null
    if (layer.type === 'object') return 'object'
    return layer.hex ? 'hex-bg' : 'image-bg'
  }

  const syncFrame = () => {
    const g = frameGroup.current
    const rect = frameRect.current
    if (!g || !rect) return
    const kind = selectedKind()
    const node = selectedNode()
    let box: { cx: number; cy: number; w: number; h: number; rot: number } | null = null

    if (kind === 'object' && node) {
      const child = node instanceof Konva.Group ? node.getChildren()[0] : node
      box = {
        cx: origin.x + node.x(),
        cy: origin.y + node.y(),
        w: (child?.width() ?? 0) * node.scaleX() + FRAME_PAD * 2,
        h: (child?.height() ?? 0) * node.scaleY() + FRAME_PAD * 2,
        rot: node.rotation(),
      }
    } else if (kind === 'image-bg' && proxy.current) {
      // Le cadre suit le mandataire : il reste la zone de debordement, et ne
      // bouge que pendant un zoom ou une rotation aux poignees.
      const px = proxy.current
      box = { cx: px.x(), cy: px.y(), w: px.width() * px.scaleX(), h: px.height() * px.scaleY(), rot: px.rotation() }
    } else if (kind === 'hex-bg') {
      box = {
        cx: ghost.x + ghost.w / 2,
        cy: ghost.y + ghost.h / 2,
        w: ghost.w - FRAME_INSET * 2,
        h: ghost.h - FRAME_INSET * 2,
        rot: 0,
      }
    }

    g.visible(!!box)
    if (box) {
      g.position({ x: box.cx, y: box.cy })
      g.rotation(box.rot)
      const x = -box.w / 2
      const y = -box.h / 2
      rect.setAttrs({ x, y, width: box.w, height: box.h })
      const arm = Math.min(FRAME_ARM, box.w / 3, box.h / 3)
      const corners = frameCorners(x, y, box.w, box.h)
      frameLines.current.forEach((line, i) => {
        const [cx, cy, dx, dy] = corners[i]
        line?.points([cx, cy + dy * arm, cx, cy, cx + dx * arm, cy])
      })
    }
    g.getLayer()?.batchDraw()
  }

  const syncTransformer = () => {
    const tr = transformer.current
    if (!tr) return
    const kind = selectedKind()
    const target = kind === 'object' ? selectedNode() : kind === 'image-bg' ? proxy.current : null
    tr.nodes(target ? [target] : [])
    tr.getLayer()?.batchDraw()
  }

  // Contrainte de couverture appliquee EN DIRECT sur un fond en cours de
  // manipulation. Ne l'appliquer qu'au relachement laissait, le temps du
  // geste, un fond plus petit que la planche : ses bords apparaissaient a
  // gauche et a droite, puis tout sautait en place. Meme calcul que le rendu.
  const constrainBackground = (node: Konva.Node) => {
    const idx = selectedRef.current
    const layer = idx === null ? undefined : layersRef.current[idx]
    if (!layer || layer.type !== 'background' || !(node instanceof Konva.Group)) return
    const child = node.getChildren()[0] as Konva.Image | undefined
    const img = child?.image() as HTMLImageElement | undefined
    if (!child || !img) return
    const eff = child.width() / skinWidth // echelle effective quand scale() vaut 1
    const cov = coverBackground(
      {
        ...layer,
        scale: eff * node.scaleX(),
        rotation: node.rotation(),
        x: node.x() / skinWidth,
        y: node.y() / skinHeight,
      },
      img,
      skinWidth,
      skinHeight,
    )
    const zoom = cov.scale / eff
    node.scale({ x: zoom, y: zoom })
    node.position({ x: cov.x * skinWidth, y: cov.y * skinHeight })
  }

  // --- Glisser le fond, depuis sa silhouette dans le canvas du dessus -------
  //
  // `bgHit` ne bouge jamais : sa fonction de bornage renvoie toujours sa
  // position de depart. On ne s'en sert que pour lire le deplacement du doigt,
  // qu'on reporte sur le vrai noeud, en bas, borne par la couverture.
  const onBgDragStart = () => {
    const node = nodes.current.get(bgIndex)
    const hit = bgHit.current
    if (!node || !hit) return
    bgDrag.current = { hit: hit.absolutePosition(), node: { x: node.x(), y: node.y() } }
  }
  const bgDragBound = (pos: { x: number; y: number }) => {
    const start = bgDrag.current
    const node = nodes.current.get(bgIndex)
    if (!start || !node) return pos
    node.position({ x: start.node.x + (pos.x - start.hit.x), y: start.node.y + (pos.y - start.hit.y) })
    constrainBackground(node)
    node.getLayer()?.batchDraw()
    return start.hit
  }
  const onBgDragEnd = () => {
    bgDrag.current = null
    // Le noeud n'a pas ete traine par Konva : on declenche nous-memes la
    // validation que le calque ecoute deja.
    nodes.current.get(bgIndex)?.fire('dragend')
  }

  // Poignees du fond : le mandataire est transforme par le Transformer, on
  // rejoue son echelle et sa rotation sur l'image (autour de son centre), dans
  // le meme sens que pour un objet -- resserrer le cadre reduit le fond,
  // l'elargir l'agrandit (on peut tirer un coin au-dela de la scene, Konva
  // suit la souris hors du canvas). Puis on remet le mandataire a plat et on
  // laisse l'image valider comme apres ses propres poignees.
  const onProxyTransformStart = () => {
    const node = selectedNode()
    if (node) proxyStart.current = { sx: node.scaleX(), rot: node.rotation() }
  }
  const onProxyTransform = () => {
    const node = selectedNode()
    const px = proxy.current
    const s0 = proxyStart.current
    if (!node || !px || !s0) return
    const zoom = s0.sx * px.scaleX()
    node.scale({ x: zoom, y: zoom })
    node.rotation(s0.rot + px.rotation())
    constrainBackground(node)
    syncFrame()
  }
  const onProxyTransformEnd = () => {
    const node = selectedNode()
    proxy.current?.setAttrs({ scaleX: 1, scaleY: 1, rotation: 0, x: ghost.x + ghost.w / 2, y: ghost.y + ghost.h / 2 })
    proxyStart.current = null
    node?.fire('transformend')
  }

  useEffect(() => {
    syncTransformer()
    syncFrame()
  }, [selectedIndex, layers])

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
    onLive: syncFrame,
    constrain: constrainBackground,
  })

  const renderLayers = (attenue: boolean, only: Layer['type']) =>
    ordered
      .filter(({ layer }) => layer.type === only)
      .map(({ layer, index }) => (
        <LayerNode
          key={`${attenue ? 'g' : 'm'}-${index}`}
          layer={layer}
          src={layer.assetId ? (urls.get(layer.assetId) ?? null) : null}
          skinWidth={skinWidth}
          skinHeight={skinHeight}
          interactive={interactive && !attenue}
          onLive={syncFrame}
          register={(node) => {
            if (attenue) return
            if (node) nodes.current.set(index, node)
            else nodes.current.delete(index)
            // L'image peut arriver apres la selection : on rattache ici aussi.
            syncTransformer()
            syncFrame()
          }}
          onSelect={() => onSelect?.(index)}
          onChange={(patch) => onChange?.(index, patch)}
        />
      ))

  return (
    <div className="skin-stack" style={{ width: stageW, height: stageH }}>
      {/* Canvas du fond : purement decoratif, rien n'y ecoute. */}
      <Stage className="skin-back" width={stageW} height={stageH} listening={false}>
        <KLayer listening={false}>
          {hasBleed && (
            <Group
              x={origin.x}
              y={origin.y}
              opacity={0.32}
              listening={false}
              clipX={-marge.x}
              clipY={-marge.top}
              clipWidth={ghost.w}
              clipHeight={ghost.h}
            >
              {renderLayers(true, 'background')}
            </Group>
          )}

          <Group x={origin.x} y={origin.y} clipFunc={clip}>
            {/* Planche vide : le degrade violet -> peche de la maquette. */}
            <Rect
              width={skinWidth}
              height={skinHeight}
              fillLinearGradientStartPoint={{ x: 0, y: 0 }}
              fillLinearGradientEndPoint={{ x: skinWidth, y: skinHeight }}
              fillLinearGradientColorStops={[0, '#7a5fb0', 0.45, '#b7a0c9', 1, '#f6c3ad']}
              listening={false}
            />
            {renderLayers(false, 'background')}
          </Group>

          {/* Contour blanc de la maquette. */}
          <Shape
            x={origin.x}
            y={origin.y}
            listening={false}
            sceneFunc={(ctx, node) => {
              traceSkin(ctx, shape, skinWidth, skinHeight)
              ctx.fillStrokeShape(node)
            }}
            stroke="#ffffff"
            strokeWidth={3}
          />
        </KLayer>
      </Stage>

      {middle}

      {/* Canvas du dessus : les objets et toute la manipulation. */}
      <Stage
        className="skin-front"
        width={stageW}
        height={stageH}
        onMouseDown={onStagePointer}
        onTouchStart={(e) => {
          // Deux doigts : le pincement prend la main sur un glisser en cours.
          if (e.evt.touches.length >= 2) bgHit.current?.stopDrag()
          gesture.onTouchStart(e)
          onStagePointer(e)
        }}
        onTouchMove={gesture.onTouchMove}
        onTouchEnd={gesture.onTouchEnd}
        style={{ touchAction: 'none' }}
      >
        <KLayer>
          {/* Prise du fond : selectionne et deplace. Elle couvre toute la zone de
              debordement, pas seulement la planche -- c'est ce que le cadre
              pointille montre, et le visiteur attrape le fond la ou il le voit,
              y compris dans la marge. Dessinee avant les objets, donc un objet
              pose dessus est touche en premier. Invisible (opacite nulle) mais
              toujours detectee : la detection ignore l'opacite. */}
          {interactive && bgLayer && (
            <Rect
              ref={bgHit}
              x={ghost.x}
              y={ghost.y}
              width={ghost.w}
              height={ghost.h}
              opacity={0}
              fill="#000000"
              draggable={!bgLayer.hex}
              dragBoundFunc={bgDragBound}
              onDragStart={onBgDragStart}
              onDragEnd={onBgDragEnd}
              onMouseDown={() => onSelect?.(bgIndex)}
              onTouchStart={() => onSelect?.(bgIndex)}
            />
          )}

          <Group x={origin.x} y={origin.y} opacity={0.32} listening={false}>
            {renderLayers(true, 'object')}
          </Group>

          <Group x={origin.x} y={origin.y} clipFunc={clip}>
            {renderLayers(false, 'object')}
          </Group>

          {/* Mandataire des poignees du fond : invisible, pas de detection. */}
          {interactive && (
            <Rect
              ref={proxy}
              x={ghost.x + ghost.w / 2}
              y={ghost.y + ghost.h / 2}
              width={ghost.w - FRAME_INSET * 2}
              height={ghost.h - FRAME_INSET * 2}
              offsetX={(ghost.w - FRAME_INSET * 2) / 2}
              offsetY={(ghost.h - FRAME_INSET * 2) / 2}
              listening={false}
              onTransformStart={onProxyTransformStart}
              onTransform={onProxyTransform}
              onTransformEnd={onProxyTransformEnd}
            />
          )}

          {/* Cadre de selection (objet, fond), pilote par syncFrame. */}
          {interactive && (
            <Group ref={frameGroup} listening={false} visible={false}>
              <Rect ref={frameRect} stroke={SKY} strokeWidth={2} dash={[12, 9]} listening={false} />
              {[0, 1, 2, 3].map((i) => (
                <Line
                  key={i}
                  ref={(el) => {
                    frameLines.current[i] = el
                  }}
                  stroke={SKY}
                  strokeWidth={8}
                  lineCap="round"
                  lineJoin="round"
                  listening={false}
                />
              ))}
            </Group>
          )}

          {interactive && (
            <Transformer
              ref={transformer}
              rotateEnabled
              keepRatio
              enabledAnchors={['top-left', 'top-right', 'bottom-left', 'bottom-right']}
              // Le cadre visible est dessine par syncFrame ; les poignees
              // restent la, discretes, aux angles.
              borderEnabled={false}
              // Assez grandes pour un doigt, assez discretes pour se fondre
              // dans les crochets du cadre.
              anchorSize={28}
              anchorCornerRadius={14}
              anchorStroke="rgba(255, 255, 255, 0.55)"
              anchorStrokeWidth={1.5}
              anchorFill="rgba(79, 195, 247, 0.45)"
              // Pour le fond, la poignee de rotation au-dessus du cadre serait
              // hors scene : on la rentre dans la zone de debordement.
              rotateAnchorOffset={selectedLayer?.type === 'background' ? -40 : 30}
              boundBoxFunc={(oldBox, newBox) => (newBox.width < 30 ? oldBox : newBox)}
            />
          )}
        </KLayer>
      </Stage>
    </div>
  )
}

const FRAME_PAD = 10
const FRAME_ARM = 34

/** Les quatre angles d'un rectangle et le sens de leurs bras : [x, y, dx, dy]. */
function frameCorners(x: number, y: number, w: number, h: number): [number, number, number, number][] {
  return [
    [x, y, 1, 1],
    [x + w, y, -1, 1],
    [x + w, y + h, -1, -1],
    [x, y + h, 1, -1],
  ]
}

type NodeProps = {
  layer: Layer
  src: string | null
  skinWidth: number
  skinHeight: number
  interactive: boolean
  /** Appele a chaque mouvement (glisser, poignees) pour faire suivre le cadre. */
  onLive: () => void
  register: (node: Konva.Node | null) => void
  onSelect: () => void
  onChange: (patch: Partial<Layer>) => void
}

/**
 * Cadrage d'un fond : il doit couvrir la planche, quoi qu'ait fait le visiteur.
 *
 * L'echelle « couvre » vaut exactement la largeur de la planche, au pixel
 * pres : deplacer le fond d'un cheveu decouvrait un bord, qui apparaissait en
 * blanc. On borne donc l'echelle par le bas, et le centre assez pour que la
 * planche reste entierement dans l'image.
 *
 * Avec une rotation, la planche vue depuis le repere de l'image est un
 * rectangle penche : on couvre son rectangle englobant (W|cos|+H|sin| par
 * W|sin|+H|cos|), et on borne le decalage du centre dans ce meme repere. C'est
 * un peu plus large que le strict necessaire, mais toujours suffisant. Meme
 * calcul que `cadrer_fond` cote serveur.
 */
export function coverBackground(
  layer: Layer,
  image: HTMLImageElement | null,
  skinWidth: number,
  skinHeight: number,
) {
  const ratio = image ? image.width / image.height : skinWidth / skinHeight
  const rad = ((layer.rotation ?? 0) * Math.PI) / 180
  const c = Math.abs(Math.cos(rad))
  const sn = Math.abs(Math.sin(rad))
  // Rectangle englobant de la planche dans le repere de l'image, en px.
  const Wp = skinWidth * c + skinHeight * sn
  const Hp = skinWidth * sn + skinHeight * c

  const couverture = Math.max(Wp / skinWidth, Hp / (skinWidth / ratio))
  const scale = Math.max(couverture, layer.scale ?? couverture)
  const w = scale * skinWidth
  const h = w / ratio

  // Decalage du centre de l'image par rapport au centre de la planche, tourne
  // dans le repere de l'image, borne, puis ramene dans celui de la planche.
  const dx = (layer.x - 0.5) * skinWidth
  const dy = (layer.y - 0.5) * skinHeight
  const cos = Math.cos(rad)
  const sin = Math.sin(rad)
  const lx = dx * cos + dy * sin
  const ly = -dx * sin + dy * cos
  const bx = Math.max(-(w - Wp) / 2, Math.min((w - Wp) / 2, lx))
  const by = Math.max(-(h - Hp) / 2, Math.min((h - Hp) / 2, ly))
  const rx = bx * cos - by * sin
  const ry = bx * sin + by * cos
  return { scale, x: 0.5 + rx / skinWidth, y: 0.5 + ry / skinHeight }
}

/** Echelle effective d'un calque : un fond sans echelle couvre la planche. */
export function effectiveScale(layer: Layer, image: HTMLImageElement | null, skinWidth: number, skinHeight: number) {
  if (layer.scale !== undefined) return layer.scale
  if (!image) return 1
  return Math.max(1, (image.width / image.height) * (skinHeight / skinWidth))
}

function LayerNode({ layer, src, skinWidth, skinHeight, interactive, onLive, register, onSelect, onChange }: NodeProps) {
  const image = useImage(src)

  if (layer.type === 'background' && layer.hex) {
    return <Rect width={skinWidth} height={skinHeight} fill={layer.hex} listening={false} />
  }

  if (!image) return null

  const fond = layer.type === 'background'
  const cadre = fond ? coverBackground(layer, image, skinWidth, skinHeight) : null
  const scale = cadre ? cadre.scale : effectiveScale(layer, image, skinWidth, skinHeight)
  const w = scale * skinWidth
  const h = (image.height / image.width) * w

  const commit = (node: Konva.Node, extra: Partial<Layer> = {}) => {
    const patch: Partial<Layer> = {
      x: node.x() / skinWidth,
      y: node.y() / skinHeight,
      rotation: node.rotation(),
      ...extra,
    }
    if (fond) {
      const borne = coverBackground({ ...layer, ...patch } as Layer, image, skinWidth, skinHeight)
      patch.x = borne.x
      patch.y = borne.y
      // On n'ecrit une echelle que si le geste en a change une : sans cela, un
      // simple deplacement figerait la couverture, que « reinitialiser le
      // fond » recalcule justement en la supprimant.
      if ('scale' in extra) patch.scale = borne.scale
    }
    onChange(patch)
  }

  return (
    <Group
      ref={register}
      x={(cadre ? cadre.x : layer.x) * skinWidth}
      y={(cadre ? cadre.y : layer.y) * skinHeight}
      rotation={layer.rotation}
      opacity={layer.opacity}
      // Un fond vit dans le canvas du bas, ou rien n'ecoute : il est deplace
      // par sa silhouette mandataire, pas par Konva.
      draggable={interactive && !fond}
      listening={interactive && !fond}
      onMouseDown={onSelect}
      onTouchStart={onSelect}
      onDragMove={onLive}
      onTransform={onLive}
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
  onLive?: () => void
  /** Borne un fond pendant le geste (couverture de la planche). */
  constrain?: (node: Konva.Node) => void
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
    opts.constrain?.(node)
    opts.onLive?.()
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
