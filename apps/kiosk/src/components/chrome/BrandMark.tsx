import { useI18n } from '../../i18n'

/** « PIMP TON SKIN » en bas a gauche : deux lignes en contour, la derniere pleine. */
export function BrandMark() {
  const { t } = useI18n()
  return (
    <div className="brand-mark" aria-hidden="true">
      <span className="outline">{t('brand.line1')}</span>
      <span>
        <span className="outline">{t('brand.line2')}</span>
        <span className="solid">{t('brand.line3')}</span>
      </span>
    </div>
  )
}
