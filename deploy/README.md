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

## 1. Verrouiller le fichier de secrets

`.env` porte le mot de passe de la base, celui du SMTP et `SECRET_KEY`, la clé
qui signe les jetons d'administration. Créé par `cp` depuis `.env.example`, ou
par un `sudo vim` sur un fichier absent, il se retrouve en `-rw-r--r--` — donc
lisible par tout compte de la machine, et parfois appartenant à root.

```bash
sudo chown "$USER:$USER" .env && chmod 600 .env
ls -l .env          # doit afficher -rw------- et votre compte
```

`bin/start.sh` le crée désormais en `600`, mais un fichier déjà en place garde
le mode qu'il a.

## 2. Fermer l'accès direct à l'API

Sans ça, `http://<ip-du-serveur>:8080` reste joignable en clair, sans TLS et
sans passer par nginx. Dans `.env` :

```bash
API_BIND=127.0.0.1
```

puis `./bin/restart.sh --all`. Vérifier depuis l'extérieur que le port 8080 ne
répond plus.

(Sur le stand c'est l'inverse : la borne joint l'API par le réseau local, donc
`API_BIND=0.0.0.0`, qui est le défaut.)

## 3. Régler la borne pour le proxy

> Étape la plus facile à oublier, et son symptôme n'est pas parlant : Chrome
> affiche *« aixam.ifrit.fr souhaite accéder à d'autres applis et services sur
> cet appareil »*. La page essaie de joindre `localhost` — c'est-à-dire le
> poste du **visiteur**, pas le serveur. `bin/build.sh --front` le signale
> désormais avant que vous ne le découvriez au navigateur.

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

Une fois deploye, ce `config.json` est **conserve d'un build a l'autre** : il
porte des valeurs d'installation, pas de code. Vous pouvez donc le corriger
directement dans `apps/api/static/kiosk/config.json` — il est lu a l'execution,
un rechargement du navigateur suffit — sans qu'une recompilation ne l'ecrase.
`--reset-config` reprend celui des sources si besoin.

## 4. PostgreSQL : conteneur ou serveur

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

**Ouvrir le pare-feu pour ce sous-reseau.** Etape facile a oublier, et son
symptome n'aide pas : avec `ufw` en `deny incoming` par defaut, les paquets
venant du pont docker sont jetes en silence. Pas de refus, pas d'erreur
d'authentification — la connexion reste simplement suspendue, et l'API se fige
sur `Waiting for application startup.`

```bash
sudo ufw status verbose                                       # actif ?
sudo ufw allow from 10.83.0.0/16 to any port 5432 proto tcp
```

La regle est limitee au sous-reseau des conteneurs : elle n'ouvre pas
PostgreSQL sur Internet.

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

Distinguer resolution de nom et blocage reseau, en cinq secondes :

```bash
docker compose run --rm api python -c "
import socket
print('host.docker.internal ->', socket.gethostbyname('host.docker.internal'))
s = socket.socket(); s.settimeout(5)
try:
    s.connect(('host.docker.internal', 5432)); print('port 5432 : ouvert')
except Exception as e:
    print('port 5432 :', e)"
```

| Resultat | Cause |
|---|---|
| `timed out` / `ConnectionTimeout` | pare-feu : la regle `ufw` ci-dessus manque, ou ne couvre pas la source |
| `Connection refused` | PostgreSQL n'ecoute pas sur cette adresse (`listen_addresses`) |
| `port 5432 : ouvert` | le reseau va bien, chercher du cote de `pg_hba` ou du mot de passe |

Verifier ce que l'hote ecoute, et la passerelle reellement attribuee :

```bash
sudo ss -lntp | grep 5432
```


```bash
docker network inspect aixam_default -f '{{range .IPAM.Config}}{{.Gateway}} {{.Subnet}}{{end}}'
```

**Basculer**, dans `.env`, en deux lignes :

```bash
#COMPOSE_PROFILES=container-db
POSTGRES_HOST=10.83.0.1
```

`10.83.0.1` est la passerelle du reseau, c'est-a-dire la premiere adresse de
`DOCKER_SUBNET` — la meme que dans `listen_addresses` et `pg_hba.conf`.
Preferez-la a `host.docker.internal` : ce nom est resolu vers l'adresse du
pont **par defaut** (`172.17.0.1`), pas vers la passerelle de notre reseau.
Le verifier au besoin :

```bash
docker compose run --rm api getent hosts host.docker.internal
```

`POSTGRES_USER`, `POSTGRES_PASSWORD` et `POSTGRES_DB` servent dans les deux
montages : rien a saisir deux fois, et aucun caractere a encoder — l'URL est
assemblee par SQLAlchemy, pas par concatenation.

Le service `db` est declare sous le profil `container-db`. Commenter la
premiere ligne suffit a ce qu'il ne soit plus dans la stack — `depends_on`
porte `required: false`, donc l'API et le worker demarrent sans lui. Il n'y a
aucune option a passer : `docker compose up -d` comme `./bin/start.sh --all`
font ce qu'il faut, et `docker compose ps` ne montre plus que deux services.

**Demarrer :**

```bash
./bin/start.sh --all
```

Le script refuse de partir si la base est hors profil et que `POSTGRES_HOST`
vaut encore `db` : l'API viserait un service qui n'existe pas et redemarrerait
en boucle. Il le demande a `docker compose config`, il ne rededuit pas le
reglage.

**Verifier :**

```bash
docker compose logs api | tail -20                 # aucune erreur de connexion
sudo -u postgres psql -d aixam -c '\dt'            # les tables sont la
```

La sauvegarde devient celle du serveur, avec vos outils habituels — c'est
precisement l'interet du montage.

## 5. nginx

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

## 6. HTTPS avec Let's Encrypt

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

## 7. Vérifier

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

## Mettre à jour le serveur

```bash
cd ~/aixam && git pull && ./bin/build.sh --all --api-image && ./bin/restart.sh --all
```

`--api-image` n'est pas optionnel dès que du Python a changé : le `Dockerfile`
fait `COPY . .`, donc le code vit **dans l'image**, pas dans un volume. Sans
reconstruction, le conteneur redémarre sur l'ancien code — sans erreur, sans
avertissement, et le correctif que vous venez de tirer reste sans effet.

Seuls `media/` et `apps/api/static/` sont montés : un changement de front seul
se contente de `./bin/build.sh --all` puis d'un rechargement du navigateur.

Le symptôme d'une image restée en arrière n'aide pas — un `ModuleNotFoundError`
sur un fichier pourtant présent dans le dépôt, ou un correctif sans effet.
`bin/start.sh` et `bin/restart.sh` préviennent désormais quand du code Python
est plus récent que la dernière construction. Pour vérifier ce que l'image
contient réellement :

```bash
docker compose run --rm api ls app/tools
```

## Delivrabilite : ne pas finir en indesirable

**Le point decisif est le domaine de `MAIL_FROM`.** Il doit etre celui que la
connexion SMTP authentifie. Sinon SPF et DKIM signent pour un domaine, l'email
en affiche un autre, et l'alignement DMARC echoue.

```bash
dig +short TXT _dmarc.<domaine>          # p=reject ? p=quarantine ?
dig +short TXT <domaine> | grep spf      # qui a le droit d'envoyer
```

Un domaine en `p=reject` fait **rejeter** l'email, pas classer en spam : le
visiteur ne recoit rien et rien ne le signale a l'expediteur. C'est le cas de
`aixam.com`, dont le SPF (`+a +mx -all`) n'autorise ni OVH ni Brevo :
expedier en `@aixam.com` depuis une boite OVH ne peut pas fonctionner sans que
le proprietaire du domaine ajoute l'expediteur a son SPF et signe en DKIM.

Le back-office previent quand les deux domaines divergent (Reglages > Envoi
des emails).

Si vous passez a Brevo, son SPF doit figurer dans le domaine expediteur
(`include:spf.brevo.com`) et ses clefs DKIM y etre publiees.

### Ce dont le code s'occupe deja

- `Date` et `Message-ID` sur chaque message : leur absence est sanctionnee
  telle quelle (`MISSING_DATE`, `MISSING_MID`), et ni Python ni smtplib ne les
  ajoutent.
- une **vraie** version texte, derivee du HTML. Un corps texte reduit a « cet
  email necessite un client HTML » est un signal a lui seul.
- `Reply-To` si `MAIL_REPLY_TO` est renseigne.
- l'envoi par une file avec backoff, qui evite les rafales.

### Ce qui reste a faire hors du code

- Publier un **DMARC** sur le domaine expediteur (`ifrit.fr` n'en a pas).
- Chauffer l'adresse : quelques envois avant le salon, pas mille d'un coup.
- Verifier le rendu chez Gmail, Outlook et Apple Mail avant l'ouverture.

## Reprendre la main sur le compte d'administration

`bootstrap()` ne cree un administrateur que s'il n'en existe **aucun** :
changer `ADMIN_EMAIL` ou `ADMIN_PASSWORD` dans `.env` apres le premier
demarrage reste sans effet, et rien ne le signale.

```bash
docker compose run --rm api python -m app.tools.reset_admin --list
docker compose run --rm api python -m app.tools.reset_admin
```

Sans arguments, la commande reprend `ADMIN_EMAIL` et `ADMIN_PASSWORD` du
`.env` ; `--email` et `--password` passent outre. Le compte est cree s'il
manque, mis a jour et reactive s'il existe. Elle refuse un domaine reserve
(`.local`, `.test`…), que la connexion rejetterait ensuite.

Sans docker : `cd apps/api && ../../.venv/bin/python -m app.tools.reset_admin`.

## Doublons de visiteurs, une fois

Les versions anterieures creaient une ligne par inscription : la meme personne
qui recommencait apparaissait deux fois. Le code ne le fait plus, et la
contrainte d'unicite l'interdit desormais — mais elle ne s'ajoute pas toute
seule a une base existante (`create_all` ne sait creer que des tables).

```bash
sudo -u postgres psql -d aixam -c "SELECT email, count(*) FROM visitors GROUP BY email HAVING count(*) > 1"
```

Si la liste n'est pas vide, voir ce qui serait fait, puis le faire :

```bash
docker compose run --rm api python -m app.tools.dedupe_visitors --dry-run
docker compose run --rm api python -m app.tools.dedupe_visitors
```

La ligne la **plus ancienne** est conservee — c'est la vraie date de premiere
venue, et celle vers laquelle les creations pointent. Elle herite de ce que
les autres avaient de plus : la verification, le consentement, et les
nom/prenom les plus recents. Creations et evenements sont rattaches **avant**
suppression : sans cela, la cle etrangere en `ON DELETE SET NULL` les
anonymiserait.

La commande est rejouable et pose la contrainte meme s'il n'y a aucun doublon.

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
