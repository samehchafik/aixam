import { useState, type PointerEvent } from 'react'
import { useI18n } from '../i18n'

/**
 * Le clavier de la borne, en HTML, dans la page elle-meme.
 *
 * Le clavier tactile de Windows est une autre fenetre : la notre, plein ecran
 * et au premier plan, finissait par passer devant lui au premier appui, et le
 * visiteur tapait a l'aveugle. Celui-ci fait partie de la scene : rien ne peut
 * le recouvrir. Les champs portent `inputMode="none"`, qui dit a Windows de ne
 * plus ouvrir le sien.
 *
 * On ajoute et on efface en fin de champ : les champs sont courts, et viser
 * un point au milieu d'un mot au doigt est plus penible qu'utile.
 *
 * Chaque touche agit au `pointerdown`, en empechant l'action par defaut : le
 * champ garde ainsi le focus (et son curseur) pendant qu'on tape.
 */
export type ModeClavier = 'texte' | 'email' | 'nombre' | 'code'

type Disposition = 'lettres' | 'symboles'

const LETTRES = [
  ['a', 'z', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
  ['q', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'm'],
  ['MAJ', 'w', 'x', 'c', 'v', 'b', 'n', "'", 'EFFACER'],
]
const SYMBOLES = [
  ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
  ['é', 'è', 'ê', 'ë', 'à', 'â', 'ç', 'ï', 'î', 'ô'],
  ['MAJ', 'ù', 'û', 'ü', 'œ', '_', '+', "'", 'EFFACER'],
]
const PAVE = [
  ['1', '2', '3'],
  ['4', '5', '6'],
  ['7', '8', '9'],
  ['EFFACER', '0', 'OK'],
]

type Props = {
  mode: ModeClavier
  /** La valeur affichee : sert a la majuscule de debut de mot. */
  valeur: string
  /**
   * Une touche, appliquee a la valeur LA PLUS RECENTE. Pas `valeur + touche` :
   * deux appuis rapides, avant que la page ait repeint, partiraient tous deux
   * de la meme valeur et le second effacerait le premier.
   */
  onChange: (modifier: (valeur: string) => string) => void
  /** La touche OK : champ suivant, ou validation. */
  onOk: () => void
  /** Majuscule d'office en debut de mot (prenom, nom). */
  majusculeAuto?: boolean
  className?: string
}

export function ClavierVirtuel({ mode, valeur, onChange, onOk, majusculeAuto = false, className = '' }: Props) {
  const { t } = useI18n()
  const [disposition, setDisposition] = useState<Disposition>(mode === 'nombre' ? 'symboles' : 'lettres')
  const [maj, setMaj] = useState(false)
  // En debut de mot, la majuscule vient seule : le visiteur n'a pas a y penser.
  const debutDeMot = majusculeAuto && (valeur === '' || /[\s-]$/.test(valeur))
  const majuscule = maj !== debutDeMot

  const appui = (e: PointerEvent, action: () => void) => {
    e.preventDefault()
    action()
  }

  const touche = (cle: string) => {
    if (cle === 'EFFACER') return onChange((v) => v.slice(0, -1))
    if (cle === 'OK') return onOk()
    if (cle === 'MAJ') return setMaj((m) => !m)
    // Le debut de mot se juge sur la valeur la plus recente, comme le reste :
    // tape vite, chaque lettre se croyait sinon en debut de mot.
    const forcee = maj
    onChange((v) => {
      const debut = majusculeAuto && (v === '' || /[\s-]$/.test(v))
      return v + (forcee !== debut ? cle.toUpperCase() : cle)
    })
    // Une majuscule pour une lettre, comme sur un telephone.
    setMaj(false)
  }

  const libelle = (cle: string) => {
    if (cle === 'EFFACER') return '⌫'
    if (cle === 'MAJ') return '⇧'
    if (cle === 'OK') return t('clavier.ok')
    return majuscule ? cle.toUpperCase() : cle
  }

  const bouton = (cle: string, classe = '') => (
    <button
      key={cle}
      type="button"
      tabIndex={-1}
      className={`touche ${classe} ${cle === 'MAJ' && majuscule ? 'active' : ''}`}
      onPointerDown={(e) => appui(e, () => touche(cle))}
    >
      {libelle(cle)}
    </button>
  )

  if (mode === 'code') {
    return (
      <div className={`clavier clavier-pave ${className}`} onPointerDown={(e) => e.preventDefault()}>
        {PAVE.map((rangee, i) => (
          <div key={i} className="rangee">
            {rangee.map((cle) => bouton(cle, cle === 'EFFACER' ? 'touche-effacer' : cle === 'OK' ? 'touche-ok' : ''))}
          </div>
        ))}
      </div>
    )
  }

  const rangees = disposition === 'lettres' ? LETTRES : SYMBOLES
  return (
    <div className={`clavier ${className}`} onPointerDown={(e) => e.preventDefault()}>
      {rangees.map((rangee, i) => (
        <div key={i} className="rangee">
          {rangee.map((cle) =>
            bouton(cle, cle === 'MAJ' ? 'touche-maj' : cle === 'EFFACER' ? 'touche-effacer' : ''),
          )}
        </div>
      ))}
      <div className="rangee">
        <button
          type="button"
          tabIndex={-1}
          className="touche touche-bascule"
          onPointerDown={(e) => appui(e, () => setDisposition((d) => (d === 'lettres' ? 'symboles' : 'lettres')))}
        >
          {disposition === 'lettres' ? '123 éà' : 'ABC'}
        </button>
        {bouton('-')}
        {mode === 'email' && bouton('@')}
        <button
          type="button"
          tabIndex={-1}
          className="touche touche-espace"
          onPointerDown={(e) => appui(e, () => onChange((v) => v + ' '))}
        >
          {t('clavier.espace')}
        </button>
        {bouton('.')}
        {mode === 'email' && (
          <button
            type="button"
            tabIndex={-1}
            className="touche touche-domaine"
            onPointerDown={(e) => appui(e, () => onChange((v) => v + '.com'))}
          >
            .com
          </button>
        )}
        {bouton('OK', 'touche-ok')}
      </div>
    </div>
  )
}
