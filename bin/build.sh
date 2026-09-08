#!/usr/bin/env bash
# Compile une SPA et la depose la ou l'API la sert.
#
#   bin/build.sh --admin      back-office -> apps/api/static/admin
#   bin/build.sh --front      borne       -> apps/api/static/kiosk
#   bin/build.sh --all        les deux
#
# apps/api/static/ est monte en volume par docker compose : une fois la SPA
# compilee, un simple rechargement du navigateur suffit. Reconstruire l'image
# de l'API n'est necessaire que si requirements.txt ou le Dockerfile bougent
# -- c'est ce que fait --docker.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATIC="$ROOT/apps/api/static"

say() { printf '\033[36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[31merreur:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,/^[^#]/ s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"
  echo "Options : --docker (reconstruit aussi l'image de l'API), -h"
}

build_one() {
  # $1 = dossier sous apps/, $2 = nom sous static/, $3 = libelle
  local src="$ROOT/apps/$1" out="$STATIC/$2"
  [ -d "$src" ] || die "$src introuvable"

  if [ ! -d "$src/node_modules" ]; then
    say "$3 : installation des dependances"
    # npm ci respecte le lock ; il echoue si le lock et package.json ont
    # diverge, auquel cas npm install remet les choses d'aplomb.
    ( cd "$src" && { npm ci || npm install; } )
  fi

  say "$3 : compilation"
  ( cd "$src" && npm run build )

  # On ne remplace que ce dossier : un build --admin ne doit pas effacer la
  # borne deja compilee a cote (ce que fait `make build-front`, qui vide tout).
  say "$3 : deploiement dans static/$2"
  mkdir -p "$STATIC"
  rm -rf "$out"
  cp -R "$src/dist" "$out"
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

command -v npm >/dev/null || die "npm introuvable"

# npm n'a jamais besoin de root, et en root il laisse node_modules/, dist/ et
# static/ appartenant a root : le build suivant, lance normalement, echoue en
# EACCES sur votre propre depot. Mieux vaut refuser que reparer au chown.
if [ "$(id -u)" -eq 0 ] && [ "${ALLOW_ROOT:-0}" != "1" ]; then
  die "ne pas lancer en root (sudo) -- relancer sans sudo, ou ALLOW_ROOT=1 si vous savez ce que vous faites"
fi

if [ $ADMIN -eq 1 ]; then build_one admin admin "back-office"; fi
if [ $FRONT -eq 1 ]; then build_one kiosk kiosk "borne"; fi

if [ $DOCKER -eq 1 ]; then
  say "reconstruction de l'image API"
  ( cd "$ROOT" && docker compose build api worker )
fi

say "termine. Demarrer avec bin/start.sh"
