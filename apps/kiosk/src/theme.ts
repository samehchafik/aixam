import { createTheme, type MantineColorsTuple } from '@mantine/core'

/** Bleu ciel des maquettes (bandeau, bouton, panneau contextuel). */
const sky: MantineColorsTuple = [
  '#e6f7ff', '#c9ecfc', '#9ddcf8', '#6ccbf4', '#4FC3F7',
  '#3DB4F2', '#2aa2e0', '#1e8ec8', '#177aad', '#0f6592',
]

export const theme = createTheme({
  fontFamily: 'Poppins, "Segoe UI", Helvetica, Arial, sans-serif',
  headings: { fontFamily: 'Poppins, "Segoe UI", Helvetica, Arial, sans-serif', fontWeight: '600' },
  primaryColor: 'sky',
  primaryShade: 4,
  colors: { sky },
  defaultRadius: 'md',
  components: {
    // Pas de portail : les surcouches restent dans la scene 16/9 mise a l'echelle.
    Tooltip: { defaultProps: { color: 'sky.9', radius: 'md', fz: 'sm', withinPortal: false } },
    Popover: { defaultProps: { withinPortal: false } },
  },
})
