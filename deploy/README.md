# Mise en ligne derrière nginx

Deux domaines, une seule stack :

| Domaine | Sert | Chemin réel dans l'API |
|---|---|---|
| `aixam.ifrit.fr` | la borne | `/kiosk/` (remonté à la racine par nginx) |
| `aixam-admin.ifrit.fr` | le back-office | `/` |

## Avant de commencer

1. **DNS** : deux enregistrements `A` (et `AAAA` si IPv6) vers l'IP du serveur.
   Sans ça, Let's Encrypt ne pourra pas valider les domaines.
2. **Ports 80 et 443 ouverts** en entrée.
3. La stack tourne : `./bin/start.sh --all`, et `curl -f localhost:8080/healthz`
   répond.

## 1. Fermer l'accès direct à l'API

Sans ça, `http://<ip-du-serveur>:8080` reste joignable en clair, sans TLS et
sans passer par nginx. Dans `.env` :

```bash
API_BIND=127.0.0.1
```

puis `./bin/restart.sh --all`. Vérifier depuis l'extérieur que le port 8080 ne
répond plus.

(Sur le stand c'est l'inverse : la borne joint l'API par le réseau local, donc
`API_BIND=0.0.0.0`, qui est le défaut.)

## 2. Régler la borne pour le proxy

`apps/kiosk/public/config.json` pointe par défaut sur `http://localhost:8080`,
ce qui ne marche pas derrière un proxy. **Laisser `apiBaseUrl` vide** : la
borne prend alors l'origine de la page, donc `https://aixam.ifrit.fr` — et
l'URL WebSocket en découle automatiquement en `wss://`.

```json
{
  "apiBaseUrl": "",
  "kioskToken": "<le token de Réglages → Bornes>",
  "demoMode": false
}
```

Puis recompiler : `./bin/build.sh --front`.

## 3. PostgreSQL : conteneur ou serveur

Par defaut la base tourne **en conteneur** (service `db`, volume `pgdata`) :
c'est le montage du stand, ou l'on ne veut rien installer sur la machine.

Sur un serveur qui a deja son PostgreSQL et ses habitudes de sauvegarde, on
peut lui confier la base. Le service `db` reste declare mais n'est pas
demarre.

**Creer le role et la base :**

```bash
sudo -u postgres createuser --pwprompt aixam
sudo -u postgres createdb --owner=aixam aixam
```

Les tables sont creees au premier demarrage de l'API : une base vide suffit.

**Rendre PostgreSQL joignable depuis le conteneur.** Le conteneur passe par la
passerelle du pont docker, `172.17.0.1` par defaut. Dans
`/etc/postgresql/16/main/postgresql.conf` :

```
listen_addresses = 'localhost,172.17.0.1'
```

Surtout pas `'*'` : ce serait ouvrir PostgreSQL sur l'interface publique.

Puis dans `pg_hba.conf`, autoriser le sous-reseau des ponts docker :

```
host    aixam    aixam    172.16.0.0/12    scram-sha-256
```

```bash
sudo systemctl restart postgresql
```

**Pointer l'API dessus**, dans `.env` :

```bash
DATABASE_URL=postgresql+psycopg://aixam:motdepasse@host.docker.internal:5432/aixam
```

`host.docker.internal` est resolu grace au `extra_hosts` du compose. Si votre
docker est trop ancien pour `host-gateway`, mettre `172.17.0.1` a la place.

**Demarrer :**

```bash
./bin/start.sh --all --host-db
```

`--host-db` ajoute `--no-deps` : sans lui, `depends_on` demarrerait quand meme
la base en conteneur. Le script refuse de partir si `DATABASE_URL` manque, ce
qui evite une API en boucle sur un hote introuvable.

**Verifier :**

```bash
docker compose logs api | tail -20                 # aucune erreur de connexion
sudo -u postgres psql -d aixam -c '\dt'            # les tables sont la
```

La sauvegarde devient celle du serveur, avec vos outils habituels — c'est
precisement l'interet du montage.

## 4. nginx

```bash
sudo apt update && sudo apt install -y nginx
sudo cp deploy/nginx/aixam.ifrit.fr.conf       /etc/nginx/sites-available/aixam.ifrit.fr
sudo cp deploy/nginx/aixam-admin.ifrit.fr.conf /etc/nginx/sites-available/aixam-admin.ifrit.fr
sudo ln -sf /etc/nginx/sites-available/aixam.ifrit.fr       /etc/nginx/sites-enabled/
sudo ln -sf /etc/nginx/sites-available/aixam-admin.ifrit.fr /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

À ce stade les deux domaines répondent **en HTTP**. Vérifier avant d'aller
plus loin — un domaine qui ne répond pas en 80 fera échouer certbot.

## 5. HTTPS avec Let's Encrypt

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d aixam.ifrit.fr -d aixam-admin.ifrit.fr --redirect
```

Certbot obtient les certificats, **réécrit lui-même les deux fichiers** pour
ajouter le bloc `443` et la redirection depuis le 80. Les fichiers de
`deploy/nginx/` sont donc l'état *avant* certbot ; après, les copies dans
`/etc/nginx` auront divergé, c'est attendu.

Le renouvellement est automatique (timer systemd `certbot.timer`). Pour le
vérifier sans attendre 60 jours :

```bash
sudo certbot renew --dry-run
```

## 6. Vérifier

```bash
curl -I https://aixam.ifrit.fr                    # la borne, 200
curl -I https://aixam-admin.ifrit.fr              # le back-office, 200
curl -I http://aixam.ifrit.fr                     # 301 vers https
curl -sI https://aixam-admin.ifrit.fr/kiosk       # 404 : la borne n'est pas ici
```

Le WebSocket ne se teste qu'au navigateur : ouvrir la borne sur deux onglets,
l'un sur `/`, l'autre sur `/#/display`, et vérifier que le grand écran suit.
Un échec ici se voit dans la console (`WebSocket connection failed`) et vient
presque toujours du bloc `location /ws/`.

## Ce que les fichiers font, et pourquoi

Les deux sont des proxys vers `http://127.0.0.1:8080`. Le back-office tient
en un seul `location` ; la borne en demande deux, pour une seule raison.

**L'API sert la borne sous `/kiosk/` et le back-office à sa racine.** Le vhost
de la borne la remonte donc à la racine de son domaine :

```nginx
location ~ ^/(api|ws|media|healthz) { proxy_pass http://127.0.0.1:8080; }
location /                          { proxy_pass http://127.0.0.1:8080/kiosk/; }
```

C'est la barre oblique finale du second `proxy_pass` qui fait la substitution :
`/` devient `/kiosk/`, `/assets/x.js` devient `/kiosk/assets/x.js`. Le bundle
est compilé avec `base: './'`, donc il fonctionne à n'importe quelle
profondeur. Le premier `location` protège ce que l'API sert à sa racine :
sans lui, `/api/kiosk/register` partirait vers `/kiosk/api/kiosk/register`.

*Variante plus simple, si la borne peut vivre sur
`https://aixam.ifrit.fr/kiosk/`* : supprimer les deux `location` et n'en
garder qu'un, `location / { proxy_pass http://127.0.0.1:8080; }`. La conf
devient identique à celle du back-office.

Trois réglages restent nécessaires quoi qu'il arrive :

- **`client_max_body_size 16m`** : `/api/relay/send` reçoit la création en
  pièce jointe base64, jusqu'à 8 Mio. Le défaut de nginx, 1 Mo, la refuserait
  en 413 — et l'email partirait sans le JPEG.
- **les en-têtes `Upgrade` et `proxy_read_timeout 3600s`** sur le vhost de la
  borne : la synchronisation des deux écrans passe par un WebSocket
  (`/ws/screens`). Sans les en-têtes la négociation échoue, sans le timeout
  nginx coupe un canal inactif au bout de 60 s et le grand écran se fige
  entre deux visiteurs. Ils sont déclarés au niveau `server`, donc hérités
  par les deux `location`.
- **`location /kiosk { return 404; }`** sur le domaine admin : deux entrées
  pour deux publics.

## Durcissement facultatif

- Restreindre le back-office à vos adresses : décommenter le `allow`/`deny`
  dans `aixam-admin.ifrit.fr.conf`.
- HSTS, une fois le HTTPS confirmé, dans le bloc `443` écrit par certbot :
  `add_header Strict-Transport-Security "max-age=31536000" always;`
- `KIOSK_BASIC_USER` / `KIOSK_BASIC_PASSWORD` dans `.env` ajoutent un HTTP
  Basic devant la borne. nginx transmet l'en-tête `Authorization`, donc ça
  fonctionne tel quel derrière le proxy.
