#!/usr/bin/env bash
# Compile une SPA et la depose la ou l'API la sert.
#
#   bin/build.sh --admin      back-office -> apps/api/static/admin
#   bin/build.sh --front      borne       -> apps/api/static/kiosk
#   bin/build.sh --all        les deux
#
# OU compile-t-on : BUILD_MODE=docker (defaut) ou local, surchargeable par
# --docker / --local. En docker, aucun node ni npm n'est requis sur la
# machine -- c'est ce qui permet de deployer sur un serveur nu. En local,
# c'est le npm du poste qui travaille : quelques secondes au lieu d'une
# minute, pratique quand on itere.
#
# En docker, les dependances vivent dans un volume nomme, jamais dans
# apps/*/node_modules : les deux modes n'ecrasent donc pas leurs
# installations respectives, et un node_modules compile sur macOS ne peut
# pas empoisonner un build Linux (esbuild livre un binaire par plateforme).
#
# Le config.json deja deploye est conserve d'un build a l'autre : il porte le
# jeton de la borne et l'adresse de l'API, des valeurs d'installation qu'on ne
# veut pas voir disparaitre en recompilant. --reset-config reprend celui des
# sources.
#
# apps/api/static/ est monte en volume par docker compose : une fois la SPA
# compilee, un simple rechargement du navigateur suffit.
#
# Le code Python, lui, est COPIE dans l'image (`COPY . .` du Dockerfile) et
# n'est pas monte. Toute modification cote API -- pas seulement
# requirements.txt ou le Dockerfile -- demande donc --api-image, sinon le
# conteneur continue de tourner sur l'ancien code sans rien signaler.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATIC="$ROOT/apps/api/static"
NODE_IMAGE="${NODE_IMAGE:-node:22-alpine}"
BUILD_MODE="${BUILD_MODE:-docker}"

say()  { printf '\033[36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mattention:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31merreur:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,/^[^#]/ s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"
  echo "Ou compiler : --docker | --local   (defaut : BUILD_MODE=$BUILD_MODE)"
  echo "Options : --api-image (obligatoire apres toute modification Python),"
  echo "          --reset-config (reprend le config.json des sources), -h"
  echo "Variables : BUILD_MODE (docker|local), NODE_IMAGE (defaut $NODE_IMAGE)"
}

# Sous sudo, on veut les fichiers produits au nom du compte reel, pas de root :
# c'est ce qui evitait le EACCES au build suivant.
OWNER_UID="$(id -u)"; OWNER_GID="$(id -g)"
if [ -n "${SUDO_UID:-}" ]; then OWNER_UID="$SUDO_UID"; OWNER_GID="${SUDO_GID:-$SUDO_UID}"; fi

build_one() {
  # $1 = dossier sous apps/, $2 = nom sous static/, $3 = libelle
  local src="$ROOT/apps/$1" out="$STATIC/$2" volume="aixam-node-$1"
  [ -d "$src" ] || die "$src introuvable"

  if [ "$BUILD_MODE" = "local" ]; then
    # Un node_modules PRESENT ne veut pas dire complet : une install
    # interrompue laisse le dossier la sans les binaires. On teste ce dont
    # `npm run build` a besoin plutot que l'existence du dossier.
    if [ ! -x "$src/node_modules/.bin/tsc" ] || [ ! -x "$src/node_modules/.bin/vite" ]; then
      say "$3 : installation des dependances (npm du poste)"
      ( cd "$src" && { npm ci --no-audit --no-fund || npm install; } )
    fi
    say "$3 : compilation locale"
    ( cd "$src" && npm run build )
  else
    say "$3 : compilation dans $NODE_IMAGE"
    # Le conteneur tourne en root pour pouvoir ecrire dans le volume des
    # dependances, puis rend tout ce qu'il a depose dans le depot au compte
    # hote -- dist/, mais aussi tsconfig.tsbuildinfo que tsc ecrit a la racine.
    docker run --rm \
      -v "$src:/app" \
      -v "$volume:/app/node_modules" \
      -w /app "$NODE_IMAGE" \
      sh -c "npm ci --no-audit --no-fund && npm run build && \
             find /app -maxdepth 1 -mindepth 1 ! -name node_modules \
               -exec chown -R $OWNER_UID:$OWNER_GID {} +"
  fi

  # On ne remplace que ce dossier : un build --admin ne doit pas effacer la
  # borne deja compilee a cote (ce que fait `make build-front`, qui vide tout).
  say "$3 : deploiement dans static/$2"
  mkdir -p "$STATIC"

  # config.json de la borne porte des valeurs d'INSTALLATION -- jeton de la
  # borne, adresse de l'API -- pas des valeurs de code. Le reprendre des
  # sources a chaque build ferait perdre le reglage du salon sans rien dire.
  local garde=""
  if [ "$2" = "kiosk" ] && [ "$RESET_CONFIG" -eq 0 ] && [ -f "$out/config.json" ]; then
    garde="$(mktemp)"
    cp "$out/config.json" "$garde"
  fi

  rm -rf "$out"
  cp -R "$src/dist" "$out"

  if [ -n "$garde" ]; then
    cp "$garde" "$out/config.json"
    rm -f "$garde"
    say "$3 : config.json en place conserve (--reset-config pour reprendre celui des sources)"
  fi
  chown -R "$OWNER_UID:$OWNER_GID" "$STATIC" 2>/dev/null || true

  # config.json est lu par le navigateur, pas par le serveur : laisse a
  # localhost, la borne appelle le poste du VISITEUR. Le symptome est une
  # demande d'acces au reseau local dans Chrome, puis rien qui fonctionne.
  if [ "$2" = "kiosk" ] && [ -f "$out/config.json" ]; then
    if grep -q '"apiBaseUrl"[[:space:]]*:[[:space:]]*"http://localhost' "$out/config.json"; then
      warn "borne : apiBaseUrl pointe sur localhost. Derriere un nom de domaine,"
      warn "        le vider dans apps/kiosk/public/config.json -- la borne prendra"
      warn "        alors l'origine de la page. (Absolu requis en mode Tauri.)"
    fi
    if grep -q '"kioskToken"[[:space:]]*:[[:space:]]*"dev-kiosk-token"' "$out/config.json"; then
      warn "borne : kioskToken est encore celui d'exemple, public dans le depot."
      warn "        Le remplacer par celui de Reglages > Bornes."
    fi
  fi
}

ADMIN=0 FRONT=0 API_IMAGE=0 RESET_CONFIG=0
[ $# -gt 0 ] || { usage; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --admin)  ADMIN=1 ;;
    --front|--kiosk) FRONT=1 ;;
    --all)    ADMIN=1; FRONT=1 ;;
    --docker) BUILD_MODE=docker ;;
    --local)  BUILD_MODE=local ;;
    --api-image) API_IMAGE=1 ;;
    --reset-config) RESET_CONFIG=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "option inconnue : $1 (voir -h)" ;;
  esac
  shift
done
[ $ADMIN -eq 1 ] || [ $FRONT -eq 1 ] || die "preciser --admin, --front ou --all"

case "$BUILD_MODE" in
  docker|local) ;;
  *) die "BUILD_MODE doit valoir docker ou local (recu : $BUILD_MODE)" ;;
esac

if [ "$BUILD_MODE" = "local" ]; then
  command -v npm >/dev/null || die "npm introuvable -- compiler en docker : BUILD_MODE=docker, ou --docker"
fi

# Le mode docker en a besoin pour compiler ; --api-image en a besoin dans les
# deux cas.
if [ "$BUILD_MODE" = "docker" ] || [ $API_IMAGE -eq 1 ]; then
  # Le conseil differe selon ce qui reclame docker : --local ne sert a rien a
  # qui veut reconstruire l'image de l'API.
  if [ "$BUILD_MODE" = "docker" ]; then
    ISSUE="ou compiler avec le npm du poste : --local"
  else
    ISSUE="--api-image reconstruit une image, docker est indispensable"
  fi
  command -v docker >/dev/null || die "docker introuvable ($ISSUE)"
  # Sous Linux, un « permission denied » sur la socket veut dire que le compte
  # n'est pas dans le groupe docker -- ce qui se corrige une fois pour toutes,
  # plutot qu'en prefixant chaque commande par sudo.
  docker info >/dev/null 2>&1 || die "le demon docker ne repond pas -- le demarrer, vous y donner acces (sudo usermod -aG docker \$USER puis se reconnecter), $ISSUE"
fi

if [ $ADMIN -eq 1 ]; then build_one admin admin "back-office"; fi
if [ $FRONT -eq 1 ]; then build_one kiosk kiosk "borne"; fi

if [ $DOCKER -eq 1 ]; then
  say "reconstruction de l'image API"
  ( cd "$ROOT" && docker compose build api worker )
  # Temoin de fraicheur, lu par start.sh et restart.sh. `find -newer` compare
  # des dates de fichiers : portable, et sans analyse de format de date.
  touch "$ROOT/.api-image-built"
fi

say "termine. Demarrer avec bin/start.sh"
