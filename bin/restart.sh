#!/usr/bin/env bash
# Arrete puis redemarre la stack.
#
#   bin/restart.sh --admin            back-office
#   bin/restart.sh --front            borne
#   bin/restart.sh --all --build      recompile les deux, puis redemarre
#
# Les donnees sont conservees : c'est un redemarrage, pas une remise a zero.
# Pour repartir d'une base vide, bin/stop.sh --volumes puis bin/start.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

say() { printf '\033[36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[31merreur:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,/^[^#]/ s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"
  echo "Options : --build (recompile avant), --local (sans docker),"
  echo "          --logs (suit les logs), -h"
}

[ $# -gt 0 ] || { usage; exit 1; }
for arg in "$@"; do
  case "$arg" in
    --admin|--front|--kiosk|--all|--build|--logs|-f|--local|--docker) ;;
    -h|--help) usage; exit 0 ;;
    *) die "option inconnue : $arg (voir -h)" ;;
  esac
done

SANS_DOCKER=0
for arg in "$@"; do if [ "$arg" = "--local" ]; then SANS_DOCKER=1; fi; done

if [ $SANS_DOCKER -eq 0 ]; then
  command -v docker >/dev/null || die "docker introuvable -- ou tout relancer sur cette machine : --local"
  docker info >/dev/null 2>&1 || die "le demon docker ne tourne pas -- ouvrir Docker Desktop, ou tout relancer sur cette machine : --local"
fi

# stop.sh sans argument : les flags de cible ne le concernent pas, ils
# servent au demarrage qui suit (quoi verifier, quelle adresse afficher).
say "redemarrage"
if [ $SANS_DOCKER -eq 1 ]; then "$ROOT/bin/stop.sh" --local; else "$ROOT/bin/stop.sh"; fi
"$ROOT/bin/start.sh" "$@"
