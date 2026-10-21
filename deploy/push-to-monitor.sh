#!/usr/bin/env bash
# Publica el tablero de TheGrid2 (desarrollo) en la Pi (producción).
#
#   ./deploy/push-to-monitor.sh            # copia, reinicia y verifica
#   ./deploy/push-to-monitor.sh --dry-run  # solo dice qué haría
#
# Todo se edita y se prueba en TheGrid2 (~/monitor). La Pi solo recibe la copia:
# no se toca a mano allá. Lo que NO viaja: screenshots, respaldos, __pycache__.
# Las credenciales (calendarios, Todoist, Nest) sí viajan, con permisos 600.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${MONITOR_HOST:-monitor}"        # alias de ~/.ssh/config del equipo de la pared
USER_="${MONITOR_USER:-pi}"
KEY="${MONITOR_KEY:-$HOME/.ssh/thegrid2_to_monitor_ed25519}"
SSH=(ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 "$USER_@$HOST")
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
RSYNC=(rsync -az --delete --itemize-changes
       --exclude '.git' --exclude '__pycache__' --exclude 'screenshots'
       --exclude '*.respaldo-*' --exclude '*.png' --exclude '*.log'
       -e "ssh -i $KEY -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8")
[ "$DRY" = "1" ] && RSYNC+=(--dry-run)

say() { printf '%s\n' "$*"; }

say "== destino: $USER_@$HOST ($(ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=8 \
      "$USER_@$HOST" 'hostname; python3 -V' 2>/dev/null | tr '\n' ' ' || echo 'SIN RESPUESTA'))"

say "== copiando el proyecto"
"${RSYNC[@]}" "$SRC"/ "$USER_@$HOST:~/monitor/" | sed 's/^/   /'

say "== copiando credenciales (600)"
"${SSH[@]}" 'mkdir -p ~/.hermes && chmod 700 ~/.hermes'
scp -q -i "$KEY" -o BatchMode=yes "$HOME/.todoist.cred" "$USER_@$HOST:.todoist.cred"
scp -q -i "$KEY" -o BatchMode=yes "$HOME/.hermes/nest_token.json" \
    "$USER_@$HOST:.hermes/nest_token.json"
"${SSH[@]}" 'chmod 600 ~/.todoist.cred ~/.hermes/nest_token.json'

say "== sincronizando el script del kiosco"
scp -q -i "$KEY" -o BatchMode=yes "$SRC/deploy/start_chromium.sh" "$USER_@$HOST:start_chromium.sh"
"${SSH[@]}" 'chmod +x ~/start_chromium.sh'

say "== instalando/actualizando el servicio de usuario"
"${SSH[@]}" 'mkdir -p ~/.config/systemd/user'
scp -q -i "$KEY" -o BatchMode=yes "$SRC/deploy/monitor.user.service" \
    "$USER_@$HOST:~/.config/systemd/user/monitor.service"
"${SSH[@]}" 'systemctl --user daemon-reload && systemctl --user enable --now monitor >/dev/null 2>&1;
             systemctl --user restart monitor; loginctl enable-linger "$USER" >/dev/null 2>&1 || true;
             sleep 1; systemctl --user is-active monitor'

[ "$DRY" = "1" ] && { say "== dry-run: no reinicié nada en la Pi"; exit 0; }

say "== verificando que la Pi responda"
for _ in $(seq 1 25); do
  code="$("${SSH[@]}" 'curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8770/api/data' || true)"
  if [ "$code" = "200" ]; then
    say "   OK: la Pi está sirviendo el tablero"
    "${SSH[@]}" 'curl -s http://127.0.0.1:8770/api/data' | python3 "$SRC/deploy/summary.py"
    exit 0
  fi
  sleep 1
done

say "   FALLA: la Pi no respondió. Revisa: ssh $USER_@$HOST 'systemctl --user status monitor'"
exit 1
