/**
 * Vue complete du back-office : l'adresse se termine par /full (voir App).
 * Lu une seule fois : avec un routage par diese, le chemin ne bouge plus de la
 * session. Les pages s'en servent aussi, pour les actions reservees a celui
 * qui installe -- la remise a zero, par exemple.
 */
export const COMPLET = /(^|\/)full\/?$/.test(window.location.pathname)
