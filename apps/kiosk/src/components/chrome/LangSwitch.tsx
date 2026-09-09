import { SegmentedControl } from '@mantine/core'
import { useApp } from '../../app-context'
import { LOCALES, useI18n, type Locale } from '../../i18n'

export function LangSwitch() {
  const { locale, setLocale } = useI18n()
  const { config } = useApp()

  // Masque tant que `showLangSwitch` n'est pas mis a true dans config.json.
  // La borne reste multilingue -- les fichiers de traduction sont la et la
  // langue de depart vient de `locale` -- seul le choix est retire au visiteur.
  if (!config.showLangSwitch) return null

  return (
    <SegmentedControl
      className="lang-switch"
      size="sm"
      radius="xl"
      value={locale}
      onChange={(value) => setLocale(value as Locale)}
      data={LOCALES.map((code) => ({ value: code, label: code.toUpperCase() }))}
    />
  )
}
