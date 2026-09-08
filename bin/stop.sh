#!/usr/bin/env bash
# Arrete la stack docker.
#
#   bin/stop.sh               arrete les conteneurs, garde les donnees
#   bin/stop.sh --volumes     supprime aussi la base et les medias (DESTRUCTIF)
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
  echo "Options : --volumes, -h"
}

VOLUMES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --volumes|-v) VOLUMES=1 ;;
    --admin|--front|--kiosk|--all)
      warn "$1 sans effet : une seule stack sert les deux SPA, tout s'arrete ensemble" ;;
    -h|--help) usage; exit 0 ;;
    *) die "option inconnue : $1 (voir -h)" ;;
  esac
  shift
done

command -v docker >/dev/null || die "docker introuvable"
docker info >/dev/null 2>&1 || die "le demon docker ne tourne pas -- rien a arreter"

cd "$ROOT"

if [ $VOLUMES -eq 1 ]; then
  # Les volumes portent la base (visiteurs, creations, file d'emails) et les
  # rendus. Une frappe de trop ici efface un salon : on demande.
  warn "--volumes efface la base (visiteurs, creations, emails en file) et les medias rendus."
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
