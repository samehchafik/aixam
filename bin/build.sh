#!/usr/bin/env bash
# Compile une SPA et la depose la ou l'API la sert. Tout passe par docker :
# aucun node, aucun npm n'est requis sur la machine.
#
#   bin/build.sh --admin      back-office -> apps/api/static/admin
#   bin/build.sh --front      borne       -> apps/api/static/kiosk
#   bin/build.sh --all        les deux
#
# La compilation tourne dans un conteneur node jetable. Les dependances
# vivent dans un volume docker nomme, jamais dans apps/*/node_modules : le
# depot reste propre, et un node_modules compile sur macOS ne peut plus
# empoisonner un build Linux (esbuild livre un binaire par plateforme).
#
# apps/api/static/ est monte en volume par docker compose : une fois la SPA
# compilee, un simple rechargement du navigateur suffit. Reconstruire l'image
# de l'API n'est necessaire que si requirements.txt ou le Dockerfile bougent
# -- c'est ce que fait --docker.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATIC="$ROOT/apps/api/static"
NODE_IMAGE="${NODE_IMAGE:-node:22-alpine}"

say() { printf '\033[36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[31merreur:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,/^[^#]/ s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"
  echo "Options : --docker (reconstruit aussi l'image de l'API), -h"
  echo "Variables : NODE_IMAGE (defaut $NODE_IMAGE)"
}

# Sous sudo, on veut les fichiers produits au nom du compte reel, pas de root :
# c'est ce qui evitait le EACCES au build suivant.
OWNER_UID="$(id -u)"; OWNER_GID="$(id -g)"
if [ -n "${SUDO_UID:-}" ]; then OWNER_UID="$SUDO_UID"; OWNER_GID="${SUDO_GID:-$SUDO_UID}"; fi

build_one() {
  # $1 = dossier sous apps/, $2 = nom sous static/, $3 = libelle
  local src="$ROOT/apps/$1" out="$STATIC/$2" volume="aixam-node-$1"
  [ -d "$src" ] || die "$src introuvable"

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

  # On ne remplace que ce dossier : un build --admin ne doit pas effacer la
  # borne deja compilee a cote (ce que fait `make build-front`, qui vide tout).
  say "$3 : deploiement dans static/$2"
  mkdir -p "$STATIC"
  rm -rf "$out"
  cp -R "$src/dist" "$out"
  chown -R "$OWNER_UID:$OWNER_GID" "$STATIC" 2>/dev/null || true
}

ADMIN=0 FRONT=0 DOCKER=0
[ $# -gt 0 ] || { usage; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --admin)  ADMIN=1 ;;
    --front|--kiosk) FRONT=1 ;;
    --all)    ADMIN=1; FRONT=1 ;;
    --docker) DOCKER=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "option inconnue : $1 (voir -h)" ;;
  esac
  shift
done
[ $ADMIN -eq 1 ] || [ $FRONT -eq 1 ] || die "preciser --admin, --front ou --all"

command -v docker >/dev/null || die "docker introuvable"
# Sous Linux, un « permission denied » sur la socket veut dire que le compte
# n'est pas dans le groupe docker -- ce qui se corrige une fois pour toutes,
# plutot qu'en prefixant chaque commande par sudo.
docker info >/dev/null 2>&1 || die "le demon docker ne repond pas -- le demarrer, ou vous y donner acces : sudo usermod -aG docker \$USER puis se reconnecter"

if [ $ADMIN -eq 1 ]; then build_one admin admin "back-office"; fi
if [ $FRONT -eq 1 ]; then build_one kiosk kiosk "borne"; fi

if [ $DOCKER -eq 1 ]; then
  say "reconstruction de l'image API"
  ( cd "$ROOT" && docker compose build api worker )
fi

say "termine. Demarrer avec bin/start.sh"
