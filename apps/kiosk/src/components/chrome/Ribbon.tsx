import { useI18n } from '../../i18n'

/**
 * Debord de la scene, en pixels de scene : c'est `overflow-clip-margin` sur
 * `.stage`. Le bandeau se dessine jusque-la, pour filer jusqu'au bord de
 * l'ecran quand la fenetre n'est pas exactement en 16/9.
 */
const DEBORD = 340

/** Un trace du bandeau : la courbe, et ou y commence le texte. */
type Trace = {
  /**
   * La courbe, en pixels de scene, orientee dans le SENS DE LECTURE : le texte
   * la suit du debut a la fin.
   */
  d: string
  /** Depart du texte le long de la courbe, en pixels (pas en % : voir plus bas). */
  debut: number
  /** Interlettrage, en pixels : le studio l'a regle a la main, bandeau par bandeau. */
  espacement: number
  /** Ecart entre la courbe et la ligne de base du texte, qui la centre sur le bandeau. */
  base: number
  /**
   * Le bandeau passe DERRIERE le tableau de bord de la photo : il est coupe
   * net a cette hauteur, celle du rebord. Un ordre de calques n'y suffirait
   * pas -- aux ecrans 2 et 3, le tableau de bord est peint dans l'image.
   */
  coupe?: number
}

type Modele = {
  traces: Trace[]
  /** La pointe de fleche qui termine le bandeau, s'il en a une. */
  fleche?: string
  couleur: string
  epaisseur: number
  taille: number
}

/*
 * Les courbes sont relevees dans le fichier Illustrator des ecrans
 * (260923_BorneEasy.ai), divisees par deux : il est dessine en 3840x2160, la
 * scene en 1920x1080. Le texte y est cale lettre a lettre : chaque glyphe du
 * vectoriel est projete sur la courbe, et le depart, l'interlettrage et la
 * ligne de base sont ceux qui y posent le mieux les lettres du navigateur (a
 * 4 px pres sur tout le bandeau).
 *
 * Chaque courbe qui sort du cadre est PROLONGEE hors champ le long de sa
 * tangente : elle ne change pas a l'ecran en 16/9, mais atteint le bord de la
 * fenetre quand la scene ne la remplit pas. Le depart du texte tient compte de
 * ce prolongement -- d'ou des longueurs en pixels et non en pourcentage, qu'un
 * trace allonge aurait decales.
 */

// Le bandeau du haut des ecrans 1 a 3 : il sort de derriere le tableau de
// bord et quitte l'ecran a droite. Le texte part du tableau de bord.
const HAUT: Trace = {
  d:
    'M 1406.99 503.35 C 1406.99 503.35, 1393.67 428.4, 1432.26 379.64' +
    ' C 1508.08 283.87, 1553.25 447.18, 1652.6 385.08 C 1698.37 356.48, 1689.87 269.0, 1663.12 173.15' +
    ' C 1654.84 143.49, 1654.15 109.68, 1672.09 89.67 C 1694.17 65.04, 1737.56 65.92, 1770.75 68.97' +
    ' C 1838.37 75.18, 1901.48 131.66, 1940.05 156.35 L 2280 373.95',
  debut: 104.4,
  espacement: 0.4,
  base: 7.4,
  // Releve sur les ecrans 1 et 2 du studio : le bleu s'arrete la, a
  // l'horizontale, sur toute la largeur du bandeau.
  coupe: 395.5,
}

// Les bandeaux du bas ressortent sous le tableau de bord -- leur trace s'y
// arrete net -- et finissent en fleche. Le texte se lit depuis la fleche : la
// courbe est donc orientee de la fleche vers le tableau de bord.
const BAS_ACCUEIL: Trace = {
  d: 'M 1528.45 923.16 C 1528.45 923.16, 1804.01 923.16, 1804.01 808.67 C 1804.01 681.38, 1406.95 688.17, 1413.64 593.25',
  debut: 13.7,
  espacement: 0,
  base: 8.1,
}
const FLECHE_ACCUEIL =
  'M 1533.87 868.38 L 1549.18 979.36 C 1550.01 985.41, 1543.66 989.87, 1538.25 987.03' +
  ' L 1444.18 937.53 C 1439.36 935.0, 1438.76 928.33, 1443.06 924.98' +
  ' L 1521.82 863.49 C 1526.38 859.93, 1533.08 862.65, 1533.87 868.38 Z'

const BAS_FORMULAIRE: Trace = {
  d: 'M 1420.06 845.75 C 1420.06 845.75, 1804.01 974.55, 1804.01 808.67 C 1804.01 681.38, 1406.95 688.17, 1413.64 593.25',
  debut: 10.8,
  espacement: 0.06,
  base: 7.3,
}
const FLECHE_FORMULAIRE =
  'M 1444.22 799.88 L 1420.43 909.36 C 1419.13 915.32, 1411.63 917.33, 1407.53 912.8' +
  ' L 1336.22 833.97 C 1332.56 829.93, 1334.29 823.46, 1339.48 821.79' +
  ' L 1434.58 791.14 C 1440.09 789.37, 1445.45 794.23, 1444.22 799.88 Z'

const VAGUE = { couleur: '#3ab4e8', epaisseur: 50, taille: 24.2 }

export const RUBANS = {
  // Ecrans 4 a 7 : la vague du haut, qui entre par le haut et sort a droite.
  editeur: {
    traces: [
      {
        d:
          'M 428.3 -422.05 L 780.45 -22.05 C 780.45 -22.05, 932.83 151.06, 1226.13 147.07' +
          ' C 1519.43 143.08, 1575.28 50.43, 1697.25 50.43 C 1786.26 50.43, 1814.23 112.74, 1927.4 112.74 L 2280 112.74',
        // 68 sur le trace du studio, plus les 532,9 du prolongement.
        debut: 600.9,
        espacement: -0.27,
        base: 9.05,
      },
    ],
    couleur: '#28b7f3',
    epaisseur: 50,
    taille: 25,
  },
  // Ecran 1 et diaporama du grand ecran : la vague descend vers le bas de
  // l'ecran, la ou le tactile pose son bouton « Cree ton skin ».
  accueil: { ...VAGUE, traces: [HAUT, BAS_ACCUEIL], fleche: FLECHE_ACCUEIL },
  // Ecrans 2 et 3 : la fleche vise le formulaire.
  formulaire: { ...VAGUE, traces: [HAUT, BAS_FORMULAIRE], fleche: FLECHE_FORMULAIRE },
} satisfies Record<string, Modele>

export type NomRuban = keyof typeof RUBANS

/** Le bandeau bleu, dont le texte suit la courbe et la langue courante. */
export function Ribbon({ modele = 'editeur' }: { modele?: NomRuban }) {
  const { t } = useI18n()
  const { traces, couleur, epaisseur, taille, ...reste } = RUBANS[modele] as Modele
  const texte = `${t('ribbon')} * `.repeat(6)
  const id = `ruban-${modele}`

  return (
    <svg
      className="ribbon"
      viewBox={`${-DEBORD} ${-DEBORD} ${1920 + DEBORD * 2} ${1080 + DEBORD * 2}`}
      width={1920 + DEBORD * 2}
      height={1080 + DEBORD * 2}
      style={{ left: -DEBORD, top: -DEBORD }}
      aria-hidden="true"
    >
      <defs>
        {traces.map((trace, i) => (
          <path key={i} id={`${id}-${i}`} d={trace.d} />
        ))}
        {traces.map(
          (trace, i) =>
            trace.coupe !== undefined && (
              <clipPath key={i} id={`${id}-${i}-coupe`}>
                <rect x={-DEBORD} y={-DEBORD} width={1920 + DEBORD * 2} height={trace.coupe + DEBORD} />
              </clipPath>
            ),
        )}
      </defs>
      {traces.map((trace, i) => (
        <g key={i} clipPath={trace.coupe !== undefined ? `url(#${id}-${i}-coupe)` : undefined}>
          <use href={`#${id}-${i}`} fill="none" stroke={couleur} strokeWidth={epaisseur} />
          <text fill="#ffffff" fontSize={taille} fontWeight={600} dy={trace.base} letterSpacing={trace.espacement}>
            <textPath href={`#${id}-${i}`} startOffset={trace.debut}>
              {texte}
            </textPath>
          </text>
        </g>
      ))}
      {reste.fleche && <path d={reste.fleche} fill={couleur} />}
    </svg>
  )
}
