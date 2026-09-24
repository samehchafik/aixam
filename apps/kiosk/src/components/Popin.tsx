import type { ReactNode } from 'react'
import fermer from '../assets/fermer.svg'

/**
 * La fenetre blanche des textes longs (politique de donnees, reglement), telle
 * que l'ecran 2b la dessine : une croix, un titre, un texte qui defile.
 *
 * Un toucher hors de la fenetre la ferme aussi : sur une borne, personne ne
 * cherche la croix longtemps.
 */
export function Popin({ titre, children, onClose }: { titre: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className="popin-voile" onClick={onClose}>
      <div className="popin" role="dialog" aria-label={titre} onClick={(e) => e.stopPropagation()}>
        <button type="button" className="popin-fermer" onClick={onClose} aria-label="Fermer">
          <img src={fermer} alt="" draggable={false} />
        </button>
        <div className="popin-corps">
          <h2>{titre}</h2>
          {children}
        </div>
      </div>
    </div>
  )
}

/**
 * Un texte long, tel qu'il est ecrit dans le fichier de traduction : les
 * paragraphes separes par une ligne vide, un intertitre prefixe de « ## ».
 * Le texte se corrige ainsi sans toucher au code.
 */
export function TexteLong({ texte }: { texte: string }) {
  return (
    <>
      {texte.split(/\n\s*\n/).map((bloc, i) =>
        bloc.startsWith('## ') ? <h3 key={i}>{bloc.slice(3)}</h3> : <p key={i}>{bloc}</p>,
      )}
    </>
  )
}
