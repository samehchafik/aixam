import { useMemo, type ReactNode } from 'react'
import { Swiper, SwiperSlide } from 'swiper/react'
import { FreeMode, Scrollbar } from 'swiper/modules'
import 'swiper/css'
import 'swiper/css/free-mode'
import 'swiper/css/scrollbar'

type Props<T extends { id: string }> = {
  items: T[]
  /** Lignes du ruban. Les elements se rangent colonne par colonne. */
  rows: number
  /**
   * Largeur d'une case, en px. Une fonction donne sa largeur propre a chaque
   * colonne -- c'est ce qu'il faut pour les objets, dont les formats vont du
   * carre au tres allonge.
   */
  cellWidth: number | ((item: T) => number)
  cellHeight: number
  gap?: number
  /**
   * Decalage du ruban au repos. Il laisse une marge a gauche, se resorbe des
   * qu'on fait glisser, et n'a pas d'equivalent a droite : le contenu part en
   * coupe au bord, ce qui dit qu'il continue.
   */
  offset?: number
  selectedId?: string | null
  onSelect: (item: T) => void
  renderItem: (item: T, selected: boolean) => ReactNode
  /** Cle qui force la remise a zero (changement de langue, de catalogue). */
  resetKey?: string
}

/**
 * Le panier generique : il ne sait rien des fonds ni des objets. La cellule
 * est rendue par `renderItem`, la selection remontee par `onSelect`.
 *
 * Un ruban continu, pas des pages : le glissement est libre et s'arrete ou le
 * doigt le laisse. Les elements se rangent colonne par colonne, ce qui garde
 * cote a cote ceux qui se suivent dans le catalogue -- les trois teintes d'un
 * meme objet forment ainsi une colonne.
 *
 * Le defilement est celui de Swiper, pas celui du navigateur : sa barre est un
 * element a nous, donc toujours visible, la ou une barre native s'efface
 * d'elle-meme des qu'on ne touche plus.
 */
export function AssetSwiper<T extends { id: string }>({
  items,
  rows,
  cellWidth,
  cellHeight,
  gap = 12,
  offset = 20,
  selectedId,
  onSelect,
  renderItem,
  resetKey,
}: Props<T>) {
  const colonnes = useMemo(() => {
    const out: T[][] = []
    for (let i = 0; i < items.length; i += rows) out.push(items.slice(i, i + rows))
    return out
  }, [items, rows])

  return (
    <Swiper
      key={resetKey}
      modules={[FreeMode, Scrollbar]}
      className="asset-swiper"
      slidesPerView="auto"
      spaceBetween={gap}
      slidesOffsetBefore={offset}
      slidesOffsetAfter={0}
      freeMode={{ enabled: true, momentum: true, momentumRatio: 0.6 }}
      scrollbar={{ draggable: true }}
      touchStartPreventDefault={false}
    >
      {colonnes.map((colonne, index) => (
        <SwiperSlide
          key={index}
          style={{ width: typeof cellWidth === 'function' ? cellWidth(colonne[0]) : cellWidth }}
        >
          <div className="asset-col" style={{ gap }}>
            {colonne.map((item) => (
              <button
                key={item.id}
                type="button"
                className="asset-cell"
                style={{ height: cellHeight }}
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
