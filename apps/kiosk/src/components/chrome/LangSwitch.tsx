import { SegmentedControl } from '@mantine/core'
import { LOCALES, useI18n, type Locale } from '../../i18n'

export function LangSwitch() {
  const { locale, setLocale } = useI18n()
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
