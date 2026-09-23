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
 *
 * Elle se prolonge AUX DEUX BOUTS, hors de la scene. Sur un ecran 16/9 ces
 * prolongements sont rognes et rien ne change ; sur une fenetre d'une autre
 * proportion, la scene est plus etroite ou plus courte que la fenetre, et le
 * bandeau s'arretait en plein vide a quelques dizaines de pixels du bord --
 * alors que le decor, lui, allait jusqu'au bout.
 *
 * Les deux segments suivent la TANGENTE de la courbe a chaque extremite : ils
 * la prolongent, ils ne la redessinent pas. Et le depart est pousse plus loin
 * que le debord autorise a la scene (voir `.stage`), pour que son bout rond
 * reste toujours hors champ -- sans quoi il apparaissait en haut a gauche sur
 * une fenetre plus haute que 16/9, la ou la maquette veut une entree franche.
 */
export function Ribbon() {
  const { t } = useI18n()
  const text = `${t('ribbon')}  ✱  `
  return (
    <svg className="ribbon" viewBox="0 0 1920 240" width={1920} height={240} aria-hidden="true">
      <defs>
        <path id="ribbon-path" d="M 487 -420 L 770 -50 C 900 120, 1150 200, 1420 90 S 1750 -20, 1960 60 L 2240 167" />
      </defs>
      <use href="#ribbon-path" fill="none" stroke="#3DB4F2" strokeWidth={58} strokeLinecap="round" />
      {/* Depart du texte en unites du trace, PAS en pourcentage : un
          pourcentage se mesure sur la longueur totale, et prolonger la courbe
          aux deux bouts l'aurait decale -- le texte serait parti 30 px plus
          loin sur la planche, sans que personne n'ait demande a le bouger.
          517 = les 466 px ajoutes au depart, plus les 51 px que valaient les
          4 % d'origine. Il se pose donc exactement ou il se posait. */}
      <text fill="#ffffff" fontSize={32} fontWeight={600} dominantBaseline="middle" dy={2}>
        <textPath href="#ribbon-path" startOffset={517}>
          {text.repeat(6)}
        </textPath>
      </text>
    </svg>
  )
}
