#!/usr/bin/env bash
# Arrete la stack docker.
#
#   bin/stop.sh               arrete les conteneurs, garde les donnees
#   bin/stop.sh --local       arrete l'api et le worker lances sans docker
#   bin/stop.sh --volumes     supprime aussi la base (DESTRUCTIF)
#
# Pas de --admin ni --front ici : une seule stack sert les deux SPA, il n'y a
# rien a arreter separement. Les flags sont acceptes pour ne pas punir
# l'habitude prise avec build.sh et start.sh, mais ils ne changent rien.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

say()  { printf '\033[36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mattention:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31merreur:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,/^[^#]/ s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"
  echo "Options : --local, --volumes, -h"
}

VOLUMES=0 SANS_DOCKER=0
while [ $# -gt 0 ]; do
  case "$1" in
    --volumes|-v) VOLUMES=1 ;;
    --local) SANS_DOCKER=1 ;;
    --admin|--front|--kiosk|--all)
      warn "$1 sans effet : une seule stack sert les deux SPA, tout s'arrete ensemble" ;;
    -h|--help) usage; exit 0 ;;
    *) die "option inconnue : $1 (voir -h)" ;;
  esac
  shift
done

if [ $SANS_DOCKER -eq 1 ]; then
  # Processus lances par `bin/start.sh --local`, suivis par leur pid.
  arrete=0
  for nom in api worker; do
    pid="$ROOT/.run/$nom.pid"
    if [ -f "$pid" ] && kill -0 "$(cat "$pid")" 2>/dev/null; then
      kill "$(cat "$pid")" && arrete=$((arrete + 1))
      say "$nom arrete (pid $(cat "$pid"))"
    fi
    rm -f "$pid"
  done

  # Un pid oublie laisse un uvicorn orphelin sur le port : les redemarrages
  # suivants echouent a se lier, en silence, et start.sh voit l'ANCIEN
  # processus repondre a /healthz -- on croit alors avoir redemarre alors
  # qu'on sert toujours l'ancien code. On libere donc le port pour de bon.
  # Seulement nos uvicorn : le port peut appartenir a quelqu'un d'autre.
  PORT="$(grep -E '^API_PORT=' "$ROOT/.env" 2>/dev/null | tail -1 | cut -d= -f2 || true)"
  PORT="${PORT:-8080}"
  if command -v lsof >/dev/null; then
    for orphelin in $(lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null || true); do
      if ps -o command= -p "$orphelin" 2>/dev/null | grep -q 'uvicorn'; then
        kill "$orphelin" 2>/dev/null && arrete=$((arrete + 1))
        say "uvicorn orphelin arrete (pid $orphelin, port $PORT)"
      else
        warn "le port $PORT est pris par le pid $orphelin, qui n'est pas a nous"
      fi
    done
  fi

  [ $arrete -gt 0 ] || say "rien ne tournait"
  exit 0
fi

command -v docker >/dev/null || die "docker introuvable"
docker info >/dev/null 2>&1 || die "le demon docker ne tourne pas -- rien a arreter"

cd "$ROOT"

if [ $VOLUMES -eq 1 ]; then
  # Le seul volume nomme restant porte la base : visiteurs, creations, file
  # d'emails. Une frappe de trop ici efface un salon : on demande. Les images
  # rendues, elles, sont a un chemin fixe du depot et survivent -- mais sans
  # la base elles n'ont plus de creation a qui appartenir.
  warn "--volumes efface la base : visiteurs, creations, emails en file."
  warn "        Les images rendues restent dans apps/api/media/renders."
  printf "Taper 'oui' pour confirmer : "
  read -r answer
  [ "$answer" = "oui" ] || die "annule"
  say "arret et suppression des volumes"
  docker compose down --volumes
  say "termine. Le prochain bin/start.sh repart d'une base vide."
else
  say "arret des conteneurs (donnees conservees)"
  docker compose down
  say "termine. Relancer avec bin/start.sh --admin (ou --front, --all)."
fi
