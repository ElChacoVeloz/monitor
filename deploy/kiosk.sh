#!/usr/bin/env bash
# Kiosco: pantalla completa al tablero, sin cursor y sin apagado de pantalla.
# Uso:  MONITOR_URL=http://10.0.0.108:8770/ ./kiosk.sh
set -euo pipefail

URL="${MONITOR_URL:-http://localhost:8770/}"
BIN="${CHROMIUM:-$(command -v chromium || command -v chromium-browser || command -v google-chrome)}"

# que la pantalla no se duerma ni se apague
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true
xset s noblank 2>/dev/null || true
command -v unclutter >/dev/null && unclutter -idle 0.5 -root &

exec "$BIN" \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  --check-for-update-interval=31536000 \
  --overscroll-history-navigation=0 \
  --autoplay-policy=no-user-gesture-required \
  --hide-scrollbars \
  --start-fullscreen \
  "$URL"
