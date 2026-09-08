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
  echo "Options : --build (recompile avant), --logs (suit les logs),"
  echo "          --host-db (PostgreSQL de la machine), -h"
}

[ $# -gt 0 ] || { usage; exit 1; }
for arg in "$@"; do
  case "$arg" in
    --admin|--front|--kiosk|--all|--build|--logs|-f|--host-db) ;;
    -h|--help) usage; exit 0 ;;
    *) die "option inconnue : $arg (voir -h)" ;;
  esac
done

command -v docker >/dev/null || die "docker introuvable"
docker info >/dev/null 2>&1 || die "le demon docker ne tourne pas -- ouvrir Docker Desktop, puis relancer"

# stop.sh sans argument : les flags de cible ne le concernent pas, ils
# servent au demarrage qui suit (quoi verifier, quelle adresse afficher).
say "redemarrage"
"$ROOT/bin/stop.sh"
"$ROOT/bin/start.sh" "$@"
