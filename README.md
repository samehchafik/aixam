# AIXAM x BIG — Animation EASY

Borne multi-écran pour le **Mondial de l'Automobile 2026**.
Option 2 du brief : le visiteur compose son propre skin EASY sur un écran
tactile, le rendu s'affiche en grand sur un second écran, et il reçoit sa
création en JPEG par email.

## Architecture

```
apps/api      FastAPI + Postgres — API REST, WebSocket de sync, worker email,
              rendu serveur des créations, et sert les deux SPA
apps/admin    Back-office React (login, dashboard, visiteurs, créations,
              file d'envoi, réglages)
apps/kiosk    Front borne React (écran tactile + grand écran)
scripts       Lanceurs Chromium kiosque, générateur de catalogue de démo
```

Trois modes d'exécution pour **le même bundle** front :

| Mode | Usage | Build natif |
|---|---|---|
| Web servi par l'API | dev, recette client (lien https + login/mot de passe) | aucun |
| Chromium kiosque | salon, via `scripts/launch-kiosk.*` | aucun |
| Tauri | application `.exe` / `.dmg` / `.AppImage` | par OS |

Le code n'importe jamais `@tauri-apps/*` en dehors de `apps/kiosk/src/runtime/`.
Changer de coquille (Tauri → Electron → navigateur) ne touche que ce dossier.

## Démarrage

```bash
make setup          # copie .env, npm install
make seed           # catalogue de démo (formes générées) — à remplacer par les assets AIXAM
make up             # build des fronts + docker compose up
```

- Back-office : http://localhost:8080 (`ADMIN_EMAIL` / `ADMIN_PASSWORD` du `.env`)
- Borne : http://localhost:8080/kiosk/ (protégé par `KIOSK_BASIC_USER` / `KIOSK_BASIC_PASSWORD`)
- Grand écran : http://localhost:8080/kiosk/#/display

## Développement

```bash
docker compose up -d db
.venv/bin/uvicorn app.main:app --reload --port 8080   # depuis apps/api
cd apps/kiosk && npm run dev                          # http://localhost:5173
cd apps/admin && npm run dev                          # http://localhost:5174
```

## Installation sur le salon

1. Installer Docker, copier le dépôt, renseigner `.env` (SMTP, mots de passe).
2. `make up`.
3. Récupérer le token de la borne dans **Réglages → Bornes** du back-office.
4. Renseigner `apiBaseUrl` et `kioskToken` dans le `config.json` de la borne
   (à côté de l'exécutable Tauri, ou dans `apps/kiosk/public/config.json`).
5. Lancer `scripts/launch-kiosk.ps1` (Windows) ou `scripts/launch-kiosk.sh`.

`config.json` est lu **à l'exécution**, jamais compilé dans le bundle : changer
de host ne demande aucun rebuild.

## Points de conception

**Rendu serveur.** La création est stockée en JSON de calques (coordonnées
normalisées), pas en image. `apps/kiosk/src/components/DesignCanvas.tsx` et
`apps/api/app/services/renderer.py` interprètent le même schéma. Le JPEG envoyé
par mail est donc identique à ce que le visiteur a vu, quelle que soit la
résolution de la borne — et reste re-générable en haute définition après le
salon pour la production réelle du skin.

**File d'attente email.** Aucune requête HTTP n'envoie d'email en direct. Tout
passe par `email_outbox` et un worker séparé, avec backoff exponentiel. Une
coupure réseau sur le stand ne bloque jamais un visiteur. Le back-office
expose un **mode dégradé** qui saute la vérification email si le réseau tombe.

**Synchronisation des écrans.** WebSocket via l'API, un canal par borne, avec
mémorisation du dernier état : un écran qui redémarre en pleine animation se
resynchronise seul.

**RGPD.** Les données nominatives sont isolées sur la table `visitors`.
Supprimer un visiteur depuis l'admin efface ses données et anonymise ses
créations (`ON DELETE SET NULL`). L'export CSV ne sort par défaut que les
visiteurs ayant explicitement consenti.

## Reste à faire

- Intégrer les assets définitifs (parement EASY, 20 objets, 20 univers, polices)
  via `apps/api/media/catalog.json`.
- Charte graphique AIXAM sur les deux fronts.
- Icônes Tauri (`apps/kiosk/src-tauri/icons/`) si packaging natif retenu.
- Tests de charge et répétition générale sur le matériel réel du stand.
# aixam
