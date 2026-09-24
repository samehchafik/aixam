import { createContext, Fragment, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export const LOCALES = ['fr', 'en', 'es'] as const
export type Locale = (typeof LOCALES)[number]

type Dictionary = Record<string, unknown>
type Vars = Record<string, string | number>

type I18n = {
  locale: Locale
  setLocale: (locale: Locale) => void
  /** `t('editor.hintEmpty')`, `t('verify.wrong', { remaining: 2 })` */
  t: (key: string, vars?: Vars) => string
  /**
   * Comme `t`, mais un `{nom}` peut devenir un element : un lien, un mot mis
   * en valeur. Le texte reste entier dans le fichier de traduction, ses retours
   * a la ligne compris -- le traducteur voit la phrase, pas des morceaux.
   */
  rich: (key: string, nodes: Record<string, ReactNode>) => ReactNode
  /** Libelle multilingue d'un element de catalogue : `{ fr, en, es }`. */
  pick: (labels: Partial<Record<string, string>> | undefined) => string
}

const I18nContext = createContext<I18n | null>(null)

const cache = new Map<Locale, Dictionary>()

/**
 * Les textes vivent dans `public/locales/<lang>.json`, charges a l'execution :
 * une traduction se corrige sans recompiler la borne.
 */
async function loadDictionary(locale: Locale): Promise<Dictionary> {
  const cached = cache.get(locale)
  if (cached) return cached
  const res = await fetch(`${import.meta.env.BASE_URL}locales/${locale}.json`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`locales/${locale}.json introuvable`)
  const dict = (await res.json()) as Dictionary
  cache.set(locale, dict)
  return dict
}

function lookup(dict: Dictionary, key: string): string | undefined {
  const value = key.split('.').reduce<unknown>((node, part) => {
    if (node && typeof node === 'object') return (node as Dictionary)[part]
    return undefined
  }, dict)
  return typeof value === 'string' ? value : undefined
}

/** Remplace chaque `{nom}` d'un texte par l'element fourni. */
export function enrichir(texte: string, nodes: Record<string, ReactNode>): ReactNode {
  return texte
    .split(/\{(\w+)\}/)
    // split avec un groupe : les noms tombent aux indices impairs.
    .map((morceau, i) => <Fragment key={i}>{i % 2 ? (nodes[morceau] ?? `{${morceau}}`) : morceau}</Fragment>)
}

function interpolate(template: string, vars: Vars = {}): string {
  return template.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`))
}

export function I18nProvider({ initial, children }: { initial: string; children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(
    (LOCALES as readonly string[]).includes(initial) ? (initial as Locale) : 'fr',
  )
  const [dict, setDict] = useState<Dictionary | null>(null)

  useEffect(() => {
    let live = true
    loadDictionary(locale).then((d) => live && setDict(d))
    return () => {
      live = false
    }
  }, [locale])

  const t = useCallback(
    (key: string, vars?: Vars) => {
      const value = dict ? lookup(dict, key) : undefined
      return value ? interpolate(value, vars) : key
    },
    [dict],
  )

  const rich = useCallback((key: string, nodes: Record<string, ReactNode>) => enrichir(t(key), nodes), [t])

  const pick = useCallback(
    (labels: Partial<Record<string, string>> | undefined) =>
      labels?.[locale] ?? labels?.fr ?? Object.values(labels ?? {})[0] ?? '',
    [locale],
  )

  const value = useMemo<I18n>(
    () => ({ locale, setLocale: setLocaleState, t, rich, pick }),
    [locale, t, rich, pick],
  )

  if (!dict) return null
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18n {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('I18nProvider manquant')
  return ctx
}
