import { useI18n } from '../../i18n'

/**
 * Le bandeau ondule de la maquette. Le texte est repete le long d'une courbe
 * SVG ; il suit la langue courante.
 *
 * La courbe est relevee sur le design (2000 px de large, ramene a 1920) :
 * entre en haut vers x=790, creux a (1180, 145), remonte a (1630, 30) et
 * ressort a droite vers y=60. Il SURVOLE la planche -- d'ou le z-index dans
 * .ribbon -- et son debut hors champ est rogne par la scene, comme sur la
 * maquette.
 */
export function Ribbon() {
  const { t } = useI18n()
  const text = `${t('ribbon')}  ✱  `
  return (
    <svg className="ribbon" viewBox="0 0 1920 240" width={1920} height={240} aria-hidden="true">
      <defs>
        <path id="ribbon-path" d="M 770 -50 C 900 120, 1150 200, 1420 90 S 1750 -20, 1960 60" />
      </defs>
      <use href="#ribbon-path" fill="none" stroke="#3DB4F2" strokeWidth={58} strokeLinecap="round" />
      <text fill="#ffffff" fontSize={32} fontWeight={600} dominantBaseline="middle" dy={2}>
        <textPath href="#ribbon-path" startOffset="4%">
          {text.repeat(4)}
        </textPath>
      </text>
    </svg>
  )
}
