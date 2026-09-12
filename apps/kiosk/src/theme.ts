import { createTheme, type MantineColorsTuple } from '@mantine/core'

/**
 * Bleu interface de la charte EASY (#28b7f3), avec les deux teintes que la
 * planche de notes donne pour les etats : #3ab4e8 au doigt, #0095c9 au survol.
 */
const sky: MantineColorsTuple = [
  '#e4f6fe', '#c2ebfc', '#95dcfa', '#5ecbf7', '#28b7f3',
  '#3ab4e8', '#0095c9', '#007cab', '#00648c', '#004b89',
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
