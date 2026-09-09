#!/usr/bin/env bash
# Demarre la stack docker et dit ou regarder.
#
#   bin/start.sh --admin      back-office : http://localhost:8080
#   bin/start.sh --front      borne       : http://localhost:8080/kiosk/
#   bin/start.sh --all        les deux
#
# Une seule stack (db + api + worker) sert les deux SPA : --admin et --front
# ne demarrent pas des conteneurs differents, ils choisissent ce qu'on
# verifie avant et l'adresse qu'on affiche apres.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATIC="$ROOT/apps/api/static"

say()  { printf '\033[36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mattention:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31merreur:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,/^[^#]/ s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"
  echo "Options : --build (compile la SPA avant), --local | --docker (ou la"
  echo "          compiler, voir bin/build.sh), --logs (suit les logs), -h"
  echo "Base : reglee dans .env (COMPOSE_PROFILES / DATABASE_URL), pas ici."
  echo "Voir aussi : bin/stop.sh, bin/restart.sh"
}

ADMIN=0 FRONT=0 BUILD=0 LOGS=0 BUILD_ARGS=
[ $# -gt 0 ] || { usage; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --admin)  ADMIN=1 ;;
    --front|--kiosk) FRONT=1 ;;
    --all)    ADMIN=1; FRONT=1 ;;
    --build)  BUILD=1 ;;
    # Transmis tel quel a build.sh : ou compiler ne regarde que lui.
    --local|--docker) BUILD_ARGS="${BUILD_ARGS:-} $1" ;;
    --logs|-f) LOGS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "option inconnue : $1 (voir -h)" ;;
  esac
  shift
done
[ $ADMIN -eq 1 ] || [ $FRONT -eq 1 ] || die "preciser --admin, --front ou --all"

# --- Verifications qui evitent un message docker incomprehensible ---

# Sous Linux sans groupe docker, sudo est legitime ici -- on previent sans
# bloquer. Le .env cree et, avec --build, les dossiers compiles appartiendront
# alors a root.
# Sous sudo, on ecrit au nom du compte reel : un .env appartenant a root
# serait illisible pour la suite du travail.
OWNER_UID="$(id -u)"; OWNER_GID="$(id -g)"
if [ -n "${SUDO_UID:-}" ]; then OWNER_UID="$SUDO_UID"; OWNER_GID="${SUDO_GID:-$SUDO_UID}"; fi

command -v docker >/dev/null || die "docker introuvable"
docker info >/dev/null 2>&1 || die "le demon docker ne tourne pas -- ouvrir Docker Desktop, puis relancer"

# docker compose lit .env via env_file : sans lui, la stack ne demarre pas.
if [ ! -f "$ROOT/.env" ]; then
  say "pas de .env : copie depuis .env.example"
  cp "$ROOT/.env.example" "$ROOT/.env"
  chown "$OWNER_UID:$OWNER_GID" "$ROOT/.env" 2>/dev/null || true
  # .env porte le mot de passe de la base, celui du SMTP et la cle de
  # signature des jetons. `cp` heriterait du mode de .env.example, lisible par
  # tous : sur un serveur partage, ce serait les donner.
  chmod 600 "$ROOT/.env"
  warn "renseigner .env (mots de passe, envoi des emails) avant le salon"
fi

if [ $BUILD -eq 1 ]; then
  ARGS=()
  if [ $ADMIN -eq 1 ]; then ARGS+=(--admin); fi
  if [ $FRONT -eq 1 ]; then ARGS+=(--front); fi
  # shellcheck disable=SC2086 -- on veut la separation en mots ici.
  "$ROOT/bin/build.sh" "${ARGS[@]}" $BUILD_ARGS
fi

# Une SPA absente ne se voit qu'a l'ecran, en 503 : autant le dire ici.
check_built() {
  [ -f "$STATIC/$1/index.html" ] || die "$2 pas compile -- lancer bin/build.sh $3 (ou ajouter --build)"
}
if [ $ADMIN -eq 1 ]; then check_built admin "le back-office" --admin; fi
if [ $FRONT -eq 1 ]; then check_built kiosk "la borne" --front; fi

# --- Demarrage ---

PORT="$(grep -E '^API_PORT=' "$ROOT/.env" 2>/dev/null | tail -1 | cut -d= -f2)"
PORT="${PORT:-8080}"

# Ou tourne la base est decide par .env (COMPOSE_PROFILES), pas par ce
# script. On demande donc a compose ce qu'il va reellement demarrer, plutot
# que de re-deduire le reglage de notre cote.
SERVICES="$(cd "$ROOT" && docker compose config --services | sort | tr '\n' ' ')"
if ! printf '%s' "$SERVICES" | grep -qw db; then
  # Base hors profil, mais l'API vise toujours le service db : il n'existe
  # pas, elle redemarrerait en boucle sur un hote introuvable.
  CONFIG="$(cd "$ROOT" && docker compose config 2>/dev/null)"
  if printf '%s' "$CONFIG" | grep -qE 'POSTGRES_HOST: *db$' \
     && ! grep -qE '^DATABASE_URL=.+' "$ROOT/.env"; then
    die "base hors profil mais POSTGRES_HOST vaut encore « db » : renseigner POSTGRES_HOST dans .env (voir deploy/README.md)"
  fi
fi

say "demarrage : $SERVICES"
( cd "$ROOT" && docker compose up -d )

say "attente de l'API sur le port $PORT"
for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:$PORT/healthz" >/dev/null 2>&1; then
    READY=1; break
  fi
  sleep 1
done
if [ "${READY:-0}" != "1" ]; then
  warn "l'API ne repond toujours pas -- voir : docker compose logs api"
  exit 1
fi

echo
if [ $ADMIN -eq 1 ]; then say "back-office  http://localhost:$PORT"; fi
if [ $FRONT -eq 1 ]; then
  say "borne        http://localhost:$PORT/kiosk/"
  say "grand ecran  http://localhost:$PORT/kiosk/#/display"
  if grep -qE '^KIOSK_BASIC_USER=.+' "$ROOT/.env" 2>/dev/null; then
    say "             (protege par KIOSK_BASIC_USER / KIOSK_BASIC_PASSWORD du .env)"
  fi
fi
echo

if [ $LOGS -eq 1 ]; then exec docker compose -f "$ROOT/docker-compose.yml" logs -f api worker; fi
say "logs : make logs    arret : bin/stop.sh    redemarrage : bin/restart.sh"
