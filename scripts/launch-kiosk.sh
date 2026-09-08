#!/usr/bin/env bash
# Lancement de la borne en Chromium kiosque (macOS / Linux).
# Alternative sans build natif : deux fenetres plein ecran, une par moniteur.
#
#   HOST=http://192.168.1.10:8080 ./scripts/launch-kiosk.sh
set -euo pipefail

HOST="${HOST:-http://localhost:8080}"
TOUCH_POS="${TOUCH_POS:-0,0}"
DISPLAY_POS="${DISPLAY_POS:-1920,0}"
PROFILE_DIR="${PROFILE_DIR:-$HOME/.aixam-kiosk}"

for candidate in \
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  "$(command -v google-chrome || true)" \
  "$(command -v chromium || true)"; do
  if [ -x "$candidate" ]; then CHROME="$candidate"; break; fi
done
: "${CHROME:?Chrome/Chromium introuvable}"

COMMON=(--kiosk --no-first-run --disable-translate --disable-features=TranslateUI
        --overscroll-history-navigation=0 --autoplay-policy=no-user-gesture-required
        --disable-pinch --noerrdialogs --disable-session-crashed-bubble)

"$CHROME" "${COMMON[@]}" \
  --user-data-dir="$PROFILE_DIR/display" \
  --window-position="$DISPLAY_POS" \
  --app="$HOST/kiosk/#/display" &

"$CHROME" "${COMMON[@]}" \
  --user-data-dir="$PROFILE_DIR/touch" \
  --window-position="$TOUCH_POS" \
  --app="$HOST/kiosk/" &

wait
