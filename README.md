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

Pour ne toucher qu'une des deux SPA, `bin/` évite de tout recompiler :

```bash
bin/build.sh   --admin | --front | --all   [--docker | --local] [--api-image]
bin/start.sh   --admin | --front | --all   [--build] [--docker | --local] [--logs]
bin/restart.sh --admin | --front | --all   [--build] [--docker | --local] [--logs]
bin/stop.sh                                [--volumes]
```

**Où compiler** — `BUILD_MODE=docker` (défaut) ou `local`, surchargeable par
`--docker` / `--local` :

| Mode | Ce qu'il faut sur la machine | Pour |
|---|---|---|
| `docker` | rien | déployer sur un serveur nu |
| `local` | node et npm | itérer : quelques secondes au lieu d'une minute |

En mode docker, les dépendances vivent dans un **volume nommé**, jamais dans
`apps/*/node_modules` : les deux modes n'écrasent donc pas leurs installations
respectives, et un `node_modules` compilé sur macOS ne peut pas empoisonner un
build Linux (esbuild livre un binaire par plateforme). `NODE_IMAGE=` change
l'image.

`--api-image` reconstruit en plus l'image docker de l'API — utile seulement
quand `requirements.txt` ou le `Dockerfile` bougent, jamais pour un changement
de front.

`apps/api/static/` est monté en volume : après un `bin/build.sh`, un
rechargement du navigateur suffit, sans redémarrer quoi que ce soit. Une seule
stack sert les deux SPA — `--admin` et `--front` choisissent ce qui est
compilé et l'adresse affichée, pas des conteneurs différents. D'où l'absence
de ces flags sur `bin/stop.sh` : tout s'arrête ensemble.

`bin/stop.sh` conserve les données ; `--volumes` efface la base et demande
confirmation.

### Les ports

En docker, **un seul port** — `API_PORT`, 8080 par défaut — et deux chemins :

| | Adresse |
|---|---|
| Back-office | `http://localhost:8080` |
| Borne | `http://localhost:8080/kiosk/` |
| Grand écran | `http://localhost:8080/kiosk/#/display` |

Les ports séparés n'existent qu'en développement vite, sans docker : **5173**
pour la borne, **5174** pour le back-office (qui proxifie `/api` vers le 8080).

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

1. Installer Docker, copier le dépôt, renseigner `.env` (envoi des emails,
   mots de passe — voir **Envoi des emails** ci-dessous).
2. `make up`.
3. Récupérer le token de la borne dans **Réglages → Bornes** du back-office.
4. Renseigner `apiBaseUrl` et `kioskToken` dans le `config.json` de la borne
   (à côté de l'exécutable Tauri, ou dans `apps/kiosk/public/config.json`).
5. Lancer `scripts/launch-kiosk.ps1` (Windows) ou `scripts/launch-kiosk.sh`.

`config.json` est lu **à l'exécution**, jamais compilé dans le bundle : changer
de host ne demande aucun rebuild.

## Mise en ligne derrière nginx

Deux domaines pour une seule stack — la borne sur l'un, le back-office sur
l'autre — avec HTTPS Let's Encrypt : voir [deploy/README.md](deploy/README.md)
et les vhosts dans `deploy/nginx/`.

Deux réglages à ne pas oublier là-bas : `API_BIND=127.0.0.1` dans `.env` (sans
quoi l'API reste joignable en clair sur le 8080, hors du proxy) et
`apiBaseUrl` vide dans le `config.json` de la borne.

## Remontee des donnees du stand

Au salon, le back-office tourne sur le portable de l'equipe, avec sa propre
base : le reseau d'un stand ne se prete pas a travailler en direct sur le
serveur. **Reglages → Remontee des donnees** envoie ensuite visiteurs,
creations et evenements vers le back-office serveur.

Sens unique, par construction : le stand produit, le serveur consolide. Il n'y
a donc jamais deux versions d'une meme ligne a departager — la categorie de
bugs qui fait echouer les synchronisations bidirectionnelles.

Ce qui rend l'operation sure : `visitors` et `designs` ont des cles **UUID**,
donc une ligne garde le meme identifiant des deux cotes et se
reinsere-ou-se-met-a-jour sans remapping. Renvoyer un lot deja parti est sans
effet. Les evenements, dont la cle est un entier local, se dedoublonnent sur
`(session_id, name, created_at)`. Trois curseurs, un par table, ne sont avances
qu'apres un lot accepte : une coupure fait recommencer, jamais perdre.

Le JPEG ne voyage pas — `layers` est la source de verite et le serveur sait
re-rendre. Le chemin du rendu local et l'identifiant de borne ne voyagent pas
non plus : ils n'ont pas de sens sur le serveur.

Authentification par le meme jeton que le relais d'emails, avec sa revocation
et sa page d'admin. Cote serveur, `SYNC_SERVER_ENABLED=true` ouvre le role.

**La limite a connaitre** : sans marqueurs de suppression, un visiteur efface
cote serveur (droit a l'effacement) reapparait si vous faites un « Tout
renvoyer ». L'envoi incremental, lui, ne le ressuscite pas.

## Envoi des emails

Le code de vérification et la création en JPEG partent tous les deux par la
file `email_outbox`. Comment ils en sortent est le seul choix à faire, dans
`.env` (`MAIL_TRANSPORT`) ou à chaud dans **Réglages → Envoi des emails** :

| Transport | Ce que c'est | Quand le choisir |
|---|---|---|
| `smtp` | boîte OVH (`ssl0.ovh.net`, 587 STARTTLS ou 465 SSL) ou relais SMTP de Brevo | le port SMTP sort du réseau |
| `brevo` | API HTTP Brevo v3, en 443 | le réseau du salon filtre le 587 |
| `relay` | on n'expédie pas d'ici : un autre back-office AIXAM le fait | machine du stand, réseau invité |

**Le relais**, en deux phrases : le back-office du stand ne détient ni les
identifiants de la boîte OVH ni la clé Brevo, et n'a besoin que du 443. C'est
le back-office distant — déjà configuré, déjà connu des messageries — qui
expédie réellement. Le message est écrit dans l'outbox **locale** d'abord :
si le lien tombe, le visiteur n'attend pas, le worker retentera.

Le brancher :

1. Sur le back-office **distant** : `RELAY_SERVER_ENABLED=true`, puis
   **Réglages → Clients de relais → Créer un client**. Le token s'affiche
   **une seule fois** — seule son empreinte argon2 est conservée.
2. Sur le back-office **local** : **Réglages → Envoi des emails**, transport
   `relay`, l'URL `https://` du distant et le token. **Tester la liaison**
   répond avec le nom sous lequel la borne est enregistrée et son quota.
3. **Envoyer un email de test** valide la chaîne entière, worker compris.

### Tester

```bash
make test-mail
```

Deux scénarios, sans docker, sur un PostgreSQL joignable (celui du `docker
compose db` fait l'affaire ; sinon `TEST_PG_URL=...` pour en désigner un
autre). Chacun repart de bases neuves qu'il crée lui-même.

- `apps/api/tests/test_relay.py` — le back-office **serveur** : forme et
  stockage du token, quotas, tailles, expéditeur imposé, idempotence,
  révocation, refus du relais en cascade.
- `apps/api/tests/test_relay_chain.py` — le **trajet complet**, deux processus
  et deux bases : un visiteur s'inscrit sur la borne, l'email traverse, le
  client est coupé puis rouvert, un message déjà passé est rejoué.

Pour tester à la main, sans salon : *Réglages → Envoi des emails → Envoyer un
email de test*. Il passe par la file et le worker — c'est la chaîne entière
qui est validée, pas seulement la configuration.

Ce qui empêche la plateforme de servir de relais de spam : un token par
client, hashé et révocable d'un clic ; un quota journalier et une limite au
débit ; **l'expéditeur imposé par le serveur**, jamais choisi par le client ;
un seul destinataire par requête ; corps et pièce jointe plafonnés. Et une
idempotence sur l'identifiant du message, pour qu'un retry du worker local
n'envoie jamais le même email deux fois. Le `.env.example` détaille chaque
réglage.

## Assets, textes et catalogue

Tout ce que le studio et le client peuvent changer vit **hors du code** :

```
apps/api/media/backgrounds/index.json   fonds : ordre d'affichage + libellé fr/en/es (survol)
apps/api/media/objects/index.json       objets à poser : idem
apps/api/media/base/shape.json          géométrie de la planche (masque, encoche)
apps/kiosk/public/locales/{fr,en,es}.json  tous les textes de la borne
```

Format d'un `index.json` :

```json
{ "items": [
  { "id": "sunburst", "file": "sunburst.jpg",
    "label": { "fr": "Soleil rétro", "en": "Retro sunburst", "es": "Sol retro" } }
] }
```

L'ordre du tableau est l'ordre des vignettes. Un fichier absent est ignoré
(jamais d'écran cassé sur le stand). Formats : PNG avec transparence pour les
objets, JPG/PNG/WebP pour les fonds. Le catalogue est relu à chaque démarrage
de la borne, sans redéploiement. `make seed` génère un jeu de démonstration.

Une langue de plus = un fichier `locales/xx.json` + son code dans
`LOCALES` (`apps/kiosk/src/i18n/index.tsx`).

## Développement du front sans docker

```bash
cd apps/kiosk && npm run dev:mock     # API simulée depuis media/*/index.json
```

## Points de conception

**Rendu serveur.** La création est stockée en JSON de calques (coordonnées
normalisées), pas en image. `apps/kiosk/src/components/SkinCanvas.tsx` et
`apps/api/app/services/renderer.py` interprètent le même schéma, et le même
masque de planche (`shape.json`). Le JPEG envoyé
par mail est donc identique à ce que le visiteur a vu, quelle que soit la
résolution de la borne — et reste re-générable en haute définition après le
salon pour la production réelle du skin.

**File d'attente email.** Aucune requête HTTP n'envoie d'email en direct. Tout
passe par `email_outbox` et un worker séparé, avec backoff exponentiel. Une
coupure réseau sur le stand ne bloque jamais un visiteur. Le back-office
expose un **mode dégradé** qui saute la vérification email si le réseau tombe.

**Le transport est interchangeable.** SMTP, API Brevo ou relais vers un autre
back-office : la file, le backoff et la page « Emails » sont les mêmes dans
les trois cas — seul `apps/api/app/services/transports/` change. Le relais ne
duplique donc rien : le serveur réenfile le message dans sa propre outbox et
le traite comme les siens. Un échec dont on sait qu'il se reproduira à
l'identique (token révoqué, clé refusée) est marqué en échec tout de suite,
avec sa cause lisible dans l'admin, plutôt que de tourner huit fois pour
rien.

**Synchronisation des écrans.** WebSocket via l'API, un canal par borne, avec
mémorisation du dernier état : un écran qui redémarre en pleine animation se
resynchronise seul.

**RGPD.** Les données nominatives sont isolées sur la table `visitors`.
Supprimer un visiteur depuis l'admin efface ses données et anonymise ses
créations (`ON DELETE SET NULL`). L'export CSV ne sort par défaut que les
visiteurs ayant explicitement consenti.

## Reste à faire

- Intégrer les assets définitifs (fonds, objets, forme exacte de la planche)
  dans `apps/api/media/` — voir la section Assets.
- Charte graphique AIXAM sur les deux fronts.
- Icônes Tauri (`apps/kiosk/src-tauri/icons/`) si packaging natif retenu.
- Tests de charge et répétition générale sur le matériel réel du stand.
- Purge des pièces jointes reçues par le relais (`media/relay/`) et des rendus
  (`media/renders/`) : rien ne les efface aujourd'hui, ils grossissent avec le
  salon.
# aixam
