import { useI18n } from '../../i18n'

/**
 * Le bandeau ondule de la maquette. Le texte est repete le long d'une courbe
 * SVG ; il suit la langue courante.
 */
export function Ribbon() {
  const { t } = useI18n()
  const text = `${t('ribbon')}  ✱  `
  return (
    <svg className="ribbon" viewBox="0 0 1920 240" width={1920} height={240} aria-hidden="true">
      <defs>
        <path id="ribbon-path" d="M 790 -60 C 930 150, 1230 175, 1500 75 S 1850 -45, 2020 20" />
      </defs>
      <use href="#ribbon-path" fill="none" stroke="#3DB4F2" strokeWidth={54} strokeLinecap="round" />
      <text fill="#ffffff" fontSize={30} fontWeight={600} dominantBaseline="middle" dy={2}>
        <textPath href="#ribbon-path" startOffset="4%">
          {text.repeat(4)}
        </textPath>
      </text>
    </svg>
  )
}
