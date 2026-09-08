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

**Rendre PostgreSQL joignable depuis le conteneur.** Attention au piege : les
conteneurs ne sont **pas** sur le pont docker par defaut (`172.17.0.1`), mais
sur le reseau du projet, `aixam_default`. Le compose lui fixe le sous-reseau
`DOCKER_SUBNET`, `10.83.0.0/16` par defaut, donc la passerelle est la
premiere adresse de la plage : **`10.83.0.1`**. La valeur est hors de
172.17-172.31, la plage ou docker se sert quand il attribue un reseau seul :
un projet cree plus tard ne peut donc pas nous la prendre. Sans ce reglage docker
choisirait une plage libre au hasard, differente d'une machine a l'autre.

Si docker refuse le reseau — *« Pool overlaps with other one on this address
space »* — la plage est deja prise sur la machine. Voir ce qui est occupe :

```bash
docker network ls -q | xargs -r docker network inspect \
  -f '{{.Name}} {{range .IPAM.Config}}{{.Subnet}}{{end}}'
```

puis en choisir une libre dans `.env` — la passerelle est la premiere adresse
de la plage, a reporter dans `listen_addresses` et `pg_hba.conf` ci-dessous.

Les fichiers sont dans `/etc/postgresql/<version>/main/` — `ls /etc/postgresql`
donne la votre. Dans `postgresql.conf` :

```
listen_addresses = 'localhost,10.83.0.1'
```

Surtout pas `'*'` : ce serait ouvrir PostgreSQL sur l'interface publique.

Puis dans `pg_hba.conf`, autoriser le sous-reseau des ponts docker. **La
methode doit correspondre a celle de votre serveur**, sinon
l'authentification echoue sans que la ligne soit fautive :

```bash
sudo -u postgres psql -tAc 'SHOW password_encryption'
```

`scram-sha-256` (defaut a partir de PostgreSQL 14) ou `md5` (defaut jusqu'a
la 13). Mettre la meme valeur dans la ligne :

```
host    aixam    aixam    10.83.0.0/16    scram-sha-256
```

```bash
sudo systemctl restart postgresql
```

### Si l'API ne repond pas

Elle redemarre en boucle : le journal dit pourquoi en une ligne.

```bash
docker compose logs api | tail -30
```

| Message | Cause |
|---|---|
| `role "aixam" does not exist` | `createuser` pas fait |
| `database "aixam" does not exist` | `createdb` pas fait |
| `password authentication failed` | mot de passe, ou methode pg_hba qui ne correspond pas a `password_encryption` |
| `no pg_hba.conf entry for host "172.x.x.x"` | ligne pg_hba absente, ou PostgreSQL pas redemarre |
| `Connection refused` | `listen_addresses` n'inclut pas la passerelle (`10.83.0.1`) |
| bloque sur `Waiting for application startup.` | le TCP n'aboutit pas : mauvaise passerelle dans `listen_addresses`, ou pare-feu |
| `Servname not supported for ai_socktype` | erreur d'une URI passee telle quelle a libpq, pas de l'application : un `/`, `@`, `:` ou `?` dans le mot de passe doit y etre encode (`%2F`...). Le moteur SQLAlchemy, lui, n'est pas concerne |
| `could not translate host name "host.docker.internal"` | docker trop ancien pour `host-gateway` : mettre `172.17.0.1` dans `DATABASE_URL` |

Tester la connexion **depuis le reseau du projet**, avec le DATABASE_URL reel
du `.env` — un test depuis le pont par defaut ne prouverait rien, ce n'est pas
le reseau qu'empruntent les conteneurs :

```bash
docker compose run --rm api python -c "
from sqlalchemy import text
from app.db import engine
print('cible :', engine.url.render_as_string(hide_password=True))
with engine.connect() as c:
    print('connexion OK :', c.execute(text('select version()')).scalar()[:40])"
```

Le test passe par le moteur de l'application, pas par une URI construite a la
main : c'est le seul moyen qu'un succes ici garantisse un succes au demarrage.
Un `psycopg.connect(url)` direct donnerait des faux negatifs — libpq analyse
l'URI selon la RFC 3986, ou un `/` non encode dans le mot de passe coupe
l'adresse (`Servname not supported for ai_socktype`), alors que SQLAlchemy
transmet les champs separement et s'en accommode.

Verifier la passerelle reellement attribuee :

```bash
docker network inspect aixam_default -f '{{range .IPAM.Config}}{{.Gateway}} {{.Subnet}}{{end}}'
```

**Basculer**, dans `.env`, en deux lignes :

```bash
#COMPOSE_PROFILES=container-db
DATABASE_URL=postgresql+psycopg://aixam:motdepasse@host.docker.internal:5432/aixam
```

Le service `db` est declare sous le profil `container-db`. Commenter la
premiere ligne suffit a ce qu'il ne soit plus dans la stack — `depends_on`
porte `required: false`, donc l'API et le worker demarrent sans lui. Il n'y a
aucune option a passer : `docker compose up -d` comme `./bin/start.sh --all`
font ce qu'il faut, et `docker compose ps` ne montre plus que deux services.

`host.docker.internal` est resolu grace au `extra_hosts` du compose. Si votre
docker est trop ancien pour `host-gateway`, mettre `172.17.0.1` a la place.

**Demarrer :**

```bash
./bin/start.sh --all
```

Le script refuse de partir si la base est hors profil et que `DATABASE_URL`
manque : l'API viserait alors un hote inexistant et redemarrerait en boucle.
Il le demande a `docker compose config`, il ne rededuit pas le reglage.

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
