#!/usr/bin/env bash
# Dit pourquoi un deploiement n'a pas pris.
#
#   bin/diagnostic.sh              regarde la machine locale
#   bin/diagnostic.sh --local      idem, stack lancee sans docker
#
# Ne modifie rien. Repond aux quatre questions qui reviennent : le depot
# est-il a jour, l'image contient-elle le code tire, le navigateur recoit-il
# le bundle fraichement compile, et l'API repond-elle.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SANS_DOCKER=0
for arg in "$@"; do [ "$arg" = "--local" ] && SANS_DOCKER=1; done

titre() { printf '\n\033[36m== %s\033[0m\n' "$*"; }
ok()    { printf '  \033[32mok\033[0m      %s\n' "$*"; }
ko()    { printf '  \033[31mPROBLEME\033[0m %s\n' "$*"; }
info()  { printf '          %s\n' "$*"; }

titre "Depot"
BRANCHE="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
info "branche : $BRANCHE"
info "HEAD    : $(git log --oneline -1 2>/dev/null || echo '?')"
if [ "$BRANCHE" = "HEAD" ]; then
  ko "HEAD detachee : un \`git pull\` ne deplace rien. \`git checkout main\` d'abord."
fi
git fetch -q origin 2>/dev/null || info "(fetch impossible, mesure faite sans reseau)"
if git rev-parse --verify -q origin/"$BRANCHE" >/dev/null; then
  RETARD="$(git rev-list --count HEAD..origin/"$BRANCHE" 2>/dev/null || echo 0)"
  if [ "$RETARD" -gt 0 ]; then
    ko "$RETARD commit(s) de retard sur origin/$BRANCHE -- le \`git pull\` n'a pas pris."
  else
    ok "a jour avec origin/$BRANCHE"
  fi
else
  ko "aucune branche distante origin/$BRANCHE"
fi
SALES="$(git status --porcelain | grep -v '^??' | head -5 || true)"
if [ -n "$SALES" ]; then
  ko "des fichiers suivis sont modifies ici -- git pull refuse de les ecraser :"
  echo "$SALES" | while read -r _ fichier _; do info "$fichier"; done
fi

titre "Image de l'API"
if [ $SANS_DOCKER -eq 1 ]; then
  info "sans docker : l'API tourne depuis les sources, aucune image en jeu"
fi
TEMOIN="$ROOT/.api-image-built"
if [ $SANS_DOCKER -eq 1 ]; then
  :
elif [ ! -f "$TEMOIN" ]; then
  ko "jamais construite ici : ./bin/build.sh --api-image"
elif [ -n "$(find "$ROOT/apps/api" -name '*.py' -newer "$TEMOIN" -print -quit 2>/dev/null)" ]; then
  ko "du Python est plus recent que l'image : ./bin/build.sh --api-image"
else
  ok "image posterieure au code Python"
fi

titre "Bundles servis"
for spa in admin kiosk; do
  app=$([ "$spa" = "kiosk" ] && echo kiosk || echo admin)
  page="$ROOT/apps/api/static/$spa/index.html"
  if [ ! -f "$page" ]; then
    ko "$spa : pas compile -- ./bin/build.sh --all"
    continue
  fi
  if [ -n "$(find "$ROOT/apps/$app/src" -newer "$page" -print -quit 2>/dev/null)" ]; then
    ko "$spa : les sources sont plus recentes que le bundle -- ./bin/build.sh --all"
  else
    ok "$spa : bundle posterieur aux sources  ($(grep -o 'assets/index-[^\"]*\.js' "$page" | head -1))"
  fi
done

titre "API"
PORT="$(grep -E '^API_PORT=' "$ROOT/.env" 2>/dev/null | tail -1 | cut -d= -f2 || true)"
PORT="${PORT:-8080}"
if curl -fsS "http://localhost:$PORT/healthz" >/dev/null 2>&1; then
  ok "repond sur le port $PORT"
  SERVI="$(curl -fsS "http://localhost:$PORT/kiosk/" 2>/dev/null | grep -o 'assets/index-[^\"]*\.js' | head -1 || true)"
  ATTENDU="$(grep -o 'assets/index-[^\"]*\.js' "$ROOT/apps/api/static/kiosk/index.html" 2>/dev/null | head -1 || true)"
  if [ -n "$SERVI" ] && [ "$SERVI" != "$ATTENDU" ]; then
    ko "la borne servie ($SERVI) n'est pas celle du disque ($ATTENDU)"
  elif [ -n "$SERVI" ]; then
    ok "la borne servie est bien celle du disque"
  fi
else
  ko "aucune reponse sur http://localhost:$PORT/healthz -- stack arretee ?"
fi

titre "Adresses"
info "back-office  http://localhost:$PORT/"
info "borne        http://localhost:$PORT/kiosk/"
info "grand ecran  http://localhost:$PORT/kiosk/#/display"
info "(le grand ecran est sous /kiosk/ : /#/display sert le back-office)"
