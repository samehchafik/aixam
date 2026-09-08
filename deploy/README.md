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

## 3. nginx

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

## 4. HTTPS avec Let's Encrypt

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

## 5. Vérifier

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

- **La borne est remontée à la racine** de son domaine par la barre oblique
  finale de `proxy_pass http://aixam_api/kiosk/;`. Le bundle est compilé avec
  `base: './'`, donc il fonctionne à n'importe quelle profondeur.
- **`/api/`, `/media/` et `/ws/` passent sans réécriture** sur les deux
  domaines : la borne et le back-office les appellent en relatif.
- **`client_max_body_size 16m`** : `/api/relay/send` reçoit la création en
  pièce jointe base64, jusqu'à 8 Mio. Le défaut de nginx, 1 Mo, la refuserait
  en 413 — et l'email partirait sans le JPEG.
- **`proxy_read_timeout 3600s` sur `/ws/`** : sinon nginx coupe un canal
  inactif au bout de 60 s et le grand écran se fige entre deux visiteurs.
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
