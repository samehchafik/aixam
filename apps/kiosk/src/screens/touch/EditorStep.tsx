import { useEffect, useMemo, useState } from 'react'
import { Anchor, Box, Button, ColorPicker, Modal, Paper, Text, Tooltip, UnstyledButton } from '@mantine/core'
import { IconRefresh, IconTrash } from '@tabler/icons-react'
import { AssetSwiper } from '../../components/AssetSwiper'
import { Ribbon } from '../../components/chrome/Ribbon'
import { SkinCanvas } from '../../components/SkinCanvas'
import { useApp } from '../../app-context'
import { useI18n } from '../../i18n'
import { useSession } from '../../state/session'
import type { CatalogItem } from '../../api/client'

/** Largeur de la planche dans la scene 1920x1080, et marge de debordement visible. */
const SKIN_WIDTH = 1710
// Zone de debordement de la maquette : etroite sur les cotes, plus haute en
// bas pour accueillir le texte d'aide (mesure sur le design : 15 / 65 / 90 px
// pour 2000 de large).
const BLEED = { x: 14, top: 62, bottom: 86 }
// Le canvas couvre toute la scene 16/9 (les panneaux passent devant en DOM) :
// un objet peut sortir de la zone de debordement sans etre coupe. La planche
// est posee la ou la maquette la met.
const STAGE = { width: 1920, height: 1080 }
const ORIGIN = { x: (STAGE.width - SKIN_WIDTH) / 2, y: 92 + BLEED.top }

/** Cellule du swiper des fonds : la vignette « choisis ta couleur » ou un fond du catalogue. */
type BackgroundTile = { id: string; kind: 'color' } | { id: string; kind: 'asset'; item: CatalogItem }

const COLOR_SWATCHES = [
  '#D42B1E', '#F26B3A', '#F5C542', '#8BC34A', '#1EA97C', '#2196F3',
  '#3F51B5', '#9C27B0', '#E91E63', '#FFFFFF', '#9E9E9E', '#111111',
]

export function EditorStep() {
  const { api, bus } = useApp()
  const { t, pick, locale } = useI18n()
  const {
    catalog, layers, selectedIndex, sessionId, visitorId, firstName,
    setBackground, addObject, updateLayer, removeLayer, resetLayer, select, clearDesign,
    setRenderUrl, setStep,
  } = useSession()

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [colorOpen, setColorOpen] = useState(false)

  // Le grand ecran suit la composition en direct.
  useEffect(() => {
    bus.send({ type: 'state', step: 'editor', layers, firstName })
  }, [layers, firstName, bus])

  const backgroundTiles = useMemo<BackgroundTile[]>(
    () => [
      { id: '__color', kind: 'color' },
      ...(catalog?.backgrounds ?? []).map((item) => ({ id: item.id, kind: 'asset' as const, item })),
    ],
    [catalog],
  )

  const selected = selectedIndex === null ? null : layers[selectedIndex]
  const background = layers.find((l) => l.type === 'background')
  // Le fond en place reste surligne dans son panier ; l'objet selectionne dans le sien.
  const backgroundTileId = background?.assetId ?? (background?.hex ? '__color' : null)
  const objectTileId = selected?.type === 'object' ? (selected.assetId ?? null) : null

  const hint =
    selected === null || selected === undefined
      ? t('editor.hintEmpty')
      : selected.type === 'background'
        ? t('editor.hintBackground')
        : t('editor.hintObject')

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await api.saveDesign({ session_id: sessionId, visitor_id: visitorId, layers })
      const url = res.render_url ? `${api.base}${res.render_url}` : null
      setRenderUrl(url)
      bus.send({ type: 'finished', renderUrl: url })
      setStep('done')
    } catch {
      setError(t('editor.submitError'))
    } finally {
      setBusy(false)
    }
  }

  if (!catalog) return null

  const skinHeight = SKIN_WIDTH * (catalog.shape.height / catalog.shape.width)
  const notchWidth = (catalog.shape.notch.width / catalog.shape.width) * SKIN_WIDTH
  const notchHeight = (catalog.shape.notch.height / catalog.shape.height) * skinHeight

  return (
    <div className="editor-screen">
      {/* --- La planche ------------------------------------------------- */}
      <div className="skin-area">
        <SkinCanvas
          catalog={catalog}
          layers={layers}
          mediaBase={api.mediaBase}
          skinWidth={SKIN_WIDTH}
          bleed={BLEED}
          stage={STAGE}
          origin={ORIGIN}
          middle={<Ribbon />}
          interactive
          selectedIndex={selectedIndex}
          onSelect={select}
          onChange={updateLayer}
        />

        {selected && selectedIndex !== null && (
          <Paper
            className="notch-panel"
            radius="md"
            style={{
              width: notchWidth - 24,
              height: notchHeight - 14,
              left: ORIGIN.x + SKIN_WIDTH / 2 - (notchWidth - 24) / 2,
              top: ORIGIN.y + skinHeight - notchHeight + 10,
            }}
          >
            <UnstyledButton className="notch-action" onClick={() => removeLayer(selectedIndex)}>
              <IconTrash size={22} stroke={2} />
              <span>{selected.type === 'background' ? t('editor.deleteBackground') : t('editor.deleteObject')}</span>
            </UnstyledButton>
            <UnstyledButton className="notch-action" onClick={() => resetLayer(selectedIndex)}>
              <IconRefresh size={22} stroke={2} />
              <span>{selected.type === 'background' ? t('editor.resetBackground') : t('editor.resetObject')}</span>
            </UnstyledButton>
          </Paper>
        )}
      </div>

      <Text className="skin-hint" fs="italic">{hint}</Text>

      {/* --- Les deux paniers ------------------------------------------- */}
      <div className="panels">
        <section className="panel">
          <Text className="panel-title">{t('editor.backgroundsTitle')}</Text>
          <Paper className="panel-card" radius="lg">
            <AssetSwiper
              items={backgroundTiles}
              rows={3}
              columns={4}
              cellHeight={86}
              selectedId={backgroundTileId}
              resetKey={locale}
              onSelect={(tile) => {
                if (tile.kind === 'color') setColorOpen(true)
                else {
                  setBackground({ assetId: tile.id })
                  api.track('background_selected', { assetId: tile.id }, sessionId)
                }
              }}
              renderItem={(tile, isSelected) =>
                tile.kind === 'color' ? (
                  <div className={`tile tile-color ${isSelected ? 'selected' : ''}`}>
                    <span>{t('editor.colorTile')}</span>
                    <i className="color-wheel" />
                  </div>
                ) : (
                  <Tooltip label={pick(tile.item.label)} events={{ hover: true, focus: true, touch: true }} withArrow>
                    <div className={`tile ${isSelected ? 'selected' : ''}`}>
                      <img src={api.asset(tile.item)} alt={pick(tile.item.label)} draggable={false} />
                    </div>
                  </Tooltip>
                )
              }
            />
          </Paper>
        </section>

        <section className="panel">
          <Text className="panel-title">{t('editor.objectsTitle')}</Text>
          <Paper className="panel-card" radius="lg">
            <AssetSwiper
              items={catalog.objects}
              rows={3}
              columns={4}
              cellHeight={100}
              gap={0}
              selectedId={objectTileId}
              resetKey={locale}
              onSelect={(item) => {
                addObject(item.id)
                api.track('object_added', { assetId: item.id }, sessionId)
              }}
              renderItem={(item, isSelected) => (
                <Tooltip label={pick(item.label)} events={{ hover: true, focus: true, touch: true }} withArrow>
                  <div className={`tile tile-object ${isSelected ? 'selected' : ''}`}>
                    <img src={api.asset(item)} alt={pick(item.label)} draggable={false} />
                  </div>
                </Tooltip>
              )}
            />
          </Paper>
        </section>
      </div>

      {/* Selecteur de couleur unie. Modal plutot que popover : le swiper
          rogne tout ce qui deborde d'une vignette. */}
      <Modal
        opened={colorOpen}
        onClose={() => setColorOpen(false)}
        title={t('editor.colorPickerTitle')}
        centered
        withinPortal={false}
        radius="lg"
        size="auto"
        classNames={{ content: 'color-modal', header: 'color-modal' }}
      >
        <ColorPicker
          format="hex"
          size="xl"
          swatches={COLOR_SWATCHES}
          swatchesPerRow={6}
          value={background?.hex ?? '#D42B1E'}
          onChange={(hex) => setBackground({ hex })}
        />
        <Button className="cta" fullWidth mt="lg" radius="xl" onClick={() => setColorOpen(false)}>
          OK
        </Button>
      </Modal>

      {/* --- Actions ------------------------------------------------------ */}
      <Box className="editor-actions">
        {error && <Text c="red.4" size="sm">{error}</Text>}
        <Button className="cta" size="lg" radius="xl" disabled={layers.length === 0 || busy} onClick={submit}>
          {busy ? t('editor.sending') : t('editor.submit')}
        </Button>
        <Anchor component="button" type="button" className="restart" onClick={clearDesign}>
          {t('editor.restart')}
        </Anchor>
      </Box>
    </div>
  )
}
