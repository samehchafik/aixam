import { useMemo, type ReactNode } from 'react'
import { Swiper, SwiperSlide } from 'swiper/react'
import { Scrollbar } from 'swiper/modules'
import 'swiper/css'
import 'swiper/css/scrollbar'

type Props<T extends { id: string }> = {
  items: T[]
  /** Lignes par page. */
  rows: number
  /** Colonnes par page. */
  columns: number
  gap?: number
  selectedId?: string | null
  onSelect: (item: T) => void
  renderItem: (item: T, selected: boolean) => ReactNode
  /** Cle qui force la remise a zero du swiper (changement de langue, de catalogue). */
  resetKey?: string
}

/**
 * Grille paginee generique : ne sait rien des fonds ni des objets. La cellule
 * est rendue par `renderItem`, la selection remontee par `onSelect`.
 *
 * Chaque page est une grille CSS (rows x columns) et Swiper ne fait que le
 * defilement horizontal d'une page a l'autre : les cellules remplissent
 * exactement la largeur, rien n'est jamais rogne.
 */
export function AssetSwiper<T extends { id: string }>({
  items,
  rows,
  columns,
  gap = 12,
  selectedId,
  onSelect,
  renderItem,
  resetKey,
}: Props<T>) {
  const pages = useMemo(() => {
    const size = rows * columns
    const out: T[][] = []
    for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size))
    return out
  }, [items, rows, columns])

  return (
    <Swiper
      key={resetKey}
      modules={[Scrollbar]}
      className="asset-swiper"
      slidesPerView={1}
      spaceBetween={gap * 2}
      scrollbar={{ draggable: true }}
      touchStartPreventDefault={false}
    >
      {pages.map((page, index) => (
        <SwiperSlide key={index}>
          <div
            className="asset-page"
            style={{
              gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
              gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))`,
              gap,
            }}
          >
            {page.map((item) => (
              <button
                key={item.id}
                type="button"
                className="asset-cell"
                aria-pressed={item.id === selectedId}
                onClick={() => onSelect(item)}
              >
                {renderItem(item, item.id === selectedId)}
              </button>
            ))}
          </div>
        </SwiperSlide>
      ))}
    </Swiper>
  )
}
