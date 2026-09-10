import { createTheme, type MantineColorsTuple } from '@mantine/core'

/** Le rouge AIXAM, decline pour Mantine (index 6 = la couleur de la marque). */
const aixam: MantineColorsTuple = [
  '#ffeceb', '#ffd6d3', '#ffaba6', '#fd7c74', '#fa554a',
  '#f93c2f', '#d42b1e', '#be2417', '#a91c11', '#93140a',
]

export const theme = createTheme({
  fontFamily: '-apple-system, "Segoe UI", Helvetica, Arial, sans-serif',
  headings: { fontWeight: '650' },
  primaryColor: 'aixam',
  primaryShade: 6,
  colors: { aixam },
  defaultRadius: 'md',
  // Un back-office se lit assis et de pres : plus dense que les defauts de
  // Mantine, penses pour des sites grand public.
  components: {
    Table: { defaultProps: { verticalSpacing: 'sm', horizontalSpacing: 'md', highlightOnHover: true } },
    Card: { defaultProps: { withBorder: true, padding: 'lg', radius: 'md' } },
    Select: { defaultProps: { allowDeselect: false, checkIconPosition: 'right' } },
  },
})
