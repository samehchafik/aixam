# config.json

Ce fichier est lu **a l'execution**, jamais compile dans le bundle.
En mode application Tauri, c'est la copie placee a cote de l'executable
(`apps/kiosk/src-tauri/config.json`) qui fait foi.

| Cle | Role |
|---|---|
| `apiBaseUrl` | Host des appels REST et WebSocket. **A changer a l'installation.** |
| `kioskToken` | Token de la borne, recuperable dans Reglages > Bornes du back-office. |
| `displayMonitorIndex` | Moniteur du grand ecran (0 = principal). Mode Tauri uniquement. |
| `touchMonitorIndex` | Moniteur de l'ecran tactile. Mode Tauri uniquement. |
| `idleTimeoutSeconds` | Retour a l'accueil apres inactivite (surcharge par le back-office). |

Le bouton « Je passe » du formulaire (acces direct a l'editeur, sans inscription)
n'est pas un reglage de ce fichier : il ne parait qu'avec `?skip=true` dans
l'adresse de la borne, par exemple `https://aixam.ifrit.fr/?skip=true`.
