import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { useI18n } from '../i18n'
import fermer from '../assets/fermer.svg'

/** Un bouton qui valide la lecture : actif une fois le texte lu jusqu'au bout. */
type Validation = { libelle: string; aide: string; onValider: () => void }

/**
 * La fenetre blanche des textes longs (le reglement), telle
 * que l'ecran 2b la dessine : une croix, un titre, un texte qui defile.
 *
 * Un toucher hors de la fenetre la ferme aussi : sur une borne, personne ne
 * cherche la croix longtemps.
 *
 * Avec `validation`, un bouton s'ajoute sous le texte. Il reste inactif tant
 * que le visiteur n'a pas fait defiler le texte jusqu'au bout ; un texte assez
 * court pour tenir sans defiler l'active d'emblee.
 */
export function Popin({
  titre,
  children,
  onClose,
  validation,
}: {
  titre: string
  children: ReactNode
  onClose: () => void
  validation?: Validation
}) {
  const corps = useRef<HTMLDivElement>(null)
  const [luJusquauBout, setLu] = useState(false)

  // Une fois le bas atteint, le bouton reste actif : remonter relire un
  // article ne doit pas le retirer.
  const verifier = useCallback(() => {
    const el = corps.current
    // Un texte encore en chargement laisse la fenetre presque vide : elle
    // passerait pour lue jusqu'au bout.
    if (!el || el.querySelector('[aria-busy="true"]')) return
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 8) setLu(true)
  }, [])

  // Le texte arrive apres l'ouverture (il est charge) : on reverifie a chaque
  // changement du contenu, et si la fenetre change de taille.
  useLayoutEffect(() => {
    const el = corps.current
    if (!el) return
    verifier()
    const mutations = new MutationObserver(verifier)
    mutations.observe(el, { childList: true, subtree: true, characterData: true })
    const tailles = new ResizeObserver(verifier)
    tailles.observe(el)
    return () => {
      mutations.disconnect()
      tailles.disconnect()
    }
  }, [verifier])

  return (
    <div className="popin-voile" onClick={onClose}>
      <div className={`popin ${validation ? 'avec-validation' : ''}`} role="dialog" aria-label={titre} onClick={(e) => e.stopPropagation()}>
        <button type="button" className="popin-fermer" onClick={onClose} aria-label="Fermer">
          <img src={fermer} alt="" draggable={false} />
        </button>
        <div className="popin-corps" ref={corps} onScroll={verifier}>
          <h2>{titre}</h2>
          {children}
        </div>
        {validation && (
          <div className="popin-pied">
            <p className={`popin-aide ${luJusquauBout ? 'cache' : ''}`}>{validation.aide}</p>
            <button type="button" className="bouton bouton-bleu popin-valider" disabled={!luJusquauBout} onClick={validation.onValider}>
              {validation.libelle}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * Un texte legal, lu dans `public/legal/<nom>.<langue>.md` -- la version
 * francaise a defaut : ces textes n'existent souvent qu'en francais. Il se
 * corrige ainsi sans recompiler, comme les traductions.
 */
export function TexteLegal({ nom }: { nom: string }) {
  const { locale } = useI18n()
  const [texte, setTexte] = useState<string | null>(null)

  useEffect(() => {
    let vivant = true
    const lire = (langue: string) =>
      fetch(`${import.meta.env.BASE_URL}legal/${nom}.${langue}.md`, { cache: 'no-store' }).then((r) =>
        r.ok ? r.text() : Promise.reject(new Error(r.statusText)),
      )
    lire(locale)
      .catch(() => lire('fr'))
      .then((t) => vivant && setTexte(t))
      .catch(() => vivant && setTexte(''))
    return () => {
      vivant = false
    }
  }, [nom, locale])

  return <div aria-busy={texte === null}>{texte !== null && <TexteLong texte={texte} />}</div>
}

/**
 * Un texte long, dans un format volontairement reduit : les blocs separes par
 * une ligne vide ; « ## » pour un article, « ### » pour un sous-article ;
 * « - » pour une puce, indentee de deux espaces pour une puce de second rang.
 */
export function TexteLong({ texte }: { texte: string }) {
  return (
    <>
      {texte
        .trim()
        .split(/\n\s*\n/)
        .map((bloc, i) => {
          if (bloc.startsWith('### ')) return <h4 key={i}>{bloc.slice(4)}</h4>
          if (bloc.startsWith('## ')) return <h3 key={i}>{bloc.slice(3)}</h3>
          if (bloc.trimStart().startsWith('- ')) return <Liste key={i} lignes={bloc.split('\n')} />
          return <p key={i}>{bloc}</p>
        })}
    </>
  )
}

/** Une liste a puces, sur deux rangs au plus. */
function Liste({ lignes }: { lignes: string[] }) {
  const items: { texte: string; sous: string[] }[] = []
  for (const ligne of lignes) {
    const sous = ligne.startsWith('  ')
    const texte = ligne.trim().replace(/^- /, '')
    if (sous && items.length) items[items.length - 1].sous.push(texte)
    else items.push({ texte, sous: [] })
  }
  return (
    <ul>
      {items.map((item, i) => (
        <li key={i}>
          {item.texte}
          {item.sous.length > 0 && (
            <ul>
              {item.sous.map((s, j) => (
                <li key={j}>{s}</li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  )
}
