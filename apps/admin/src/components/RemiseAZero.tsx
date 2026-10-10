import { useState } from 'react'
import { Alert, Button, Group, Modal, Stack, Text, TextInput } from '@mantine/core'
import { api } from '../lib/api'

const MOT = 'SUPPRIMER'

/**
 * Le bouton de remise a zero d'une page (creations, visiteurs), dans la vue
 * complete seulement. Il faut taper SUPPRIMER pour confirmer -- l'API le
 * reverifie : un clic de travers entre deux visiteurs ne vide rien.
 */
export function RemiseAZero({
  libelle,
  explication,
  adresse,
  onFait,
}: {
  libelle: string
  explication: string
  /** La route DELETE, sans la confirmation. */
  adresse: string
  onFait: () => void
}) {
  const [ouvert, setOuvert] = useState(false)
  const [saisie, setSaisie] = useState('')
  const [enCours, setEnCours] = useState(false)
  const [erreur, setErreur] = useState<string | null>(null)
  // Apres coup : le nom de la sauvegarde prise avant la suppression.
  const [sauvegarde, setSauvegarde] = useState<string | null>(null)

  const fermer = () => {
    setOuvert(false)
    setSaisie('')
    setErreur(null)
    setSauvegarde(null)
  }

  const confirmer = async () => {
    setEnCours(true)
    setErreur(null)
    try {
      const reponse = await api<{ sauvegarde?: string }>(
        `${adresse}?${new URLSearchParams({ confirmation: saisie })}`,
        { method: 'DELETE' },
      )
      setSauvegarde(reponse.sauvegarde ?? '')
      onFait()
    } catch (e) {
      setErreur(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setEnCours(false)
    }
  }

  return (
    <>
      <Button variant="light" color="red" onClick={() => setOuvert(true)}>
        {libelle}
      </Button>
      <Modal opened={ouvert} onClose={fermer} title={libelle} centered>
        {sauvegarde !== null ? (
          <Stack gap="md">
            <Alert color="teal" variant="light">
              C'est fait. Une sauvegarde a été prise juste avant :
              <br />
              <strong>{sauvegarde}</strong>
              <br />
              dans le dossier <code>apps/api/backup</code> de cette machine.
            </Alert>
            <Group justify="flex-end">
              <Button onClick={fermer}>Fermer</Button>
            </Group>
          </Stack>
        ) : (
          <Stack gap="md">
            <Alert color="red" variant="light">
              {explication} Une sauvegarde est prise d'office juste avant, dans le dossier
              <code> apps/api/backup</code> de cette machine.
            </Alert>
            <Text fz="sm">
              Tapez <strong>{MOT}</strong> pour confirmer. Cette action est définitive.
            </Text>
            <TextInput
              value={saisie}
              onChange={(e) => setSaisie(e.currentTarget.value)}
              placeholder={MOT}
              aria-label="Confirmation"
              data-autofocus
            />
            {erreur && (
              <Text c="red" fz="sm">
                {erreur}
              </Text>
            )}
            <Group justify="flex-end">
              <Button variant="default" onClick={fermer}>
                Annuler
              </Button>
              <Button color="red" loading={enCours} disabled={saisie !== MOT} onClick={confirmer}>
                Tout supprimer
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </>
  )
}
