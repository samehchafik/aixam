import type { KioskConfig } from './types'

/**
 * Met l'adresse de l'API sous une forme sur laquelle on peut concatener.
 *
 * Tous les chemins de l'application commencent par « / » : les URL se
 * fabriquent en `${apiBaseUrl}${chemin}`. Une base qui finit par « / » donne
 * donc « //api/kiosk/bootstrap », que le navigateur lit comme une adresse
 * relative au protocole : il ira chercher un hote nomme « api ». Ecrire « / »
 * pour dire « la meme origine » -- ce qui est le reflexe -- suffit a rendre la
 * borne muette, avec pour seul indice un « Failed to fetch ».
 *
 * La chaine vide dit la meme chose et se concatene sans piege. On y ramene,
 * plutot que de demander a l'installateur de connaitre la subtilite.
 */
export function normaliserConfig(brut: KioskConfig): KioskConfig {
  return { ...brut, apiBaseUrl: (brut.apiBaseUrl ?? '').trim().replace(/\/+$/, '') }
}
