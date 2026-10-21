#!/usr/bin/env bash
# Deja el tablero corriendo como servicio (sobrevive reinicios y sesiones).
# Uso:  sudo bash ~/monitor/deploy/install-host.sh
set -euo pipefail

cd "$(dirname "$0")/.."
echo "== Monitor: instalando el servicio en $(hostname)"

# 1) liberar el puerto si alguien lo tiene a mano (un server.py suelto)
pid="$(ss -ltnp 2>/dev/null | grep ':8770' | sed 's/.*pid=\([0-9]*\).*/\1/' | head -1 || true)"
if [ -n "${pid:-}" ]; then
  echo "   cerrando el proceso manual en 8770 (pid $pid)"
  kill -9 "$pid" 2>/dev/null || true
  sleep 1
fi

# 2) instalar y arrancar la unidad
install -m 644 deploy/monitor.service /etc/systemd/system/monitor.service
systemctl daemon-reload
systemctl enable --now monitor
echo "   servicio habilitado y arrancado"

# 3) comprobar que de verdad responde
for _ in $(seq 1 25); do
  code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8770/api/data || true)"
  if [ "$code" = "200" ]; then
    ip="$(hostname -I | awk '{print $1}')"
    echo "   OK: http://$ip:8770/  (estado: $(systemctl is-active monitor))"
    exit 0
  fi
  sleep 1
done

echo "   FALLA: no respondió en 25 s. Revisa: journalctl -u monitor -n 40 --no-pager" >&2
exit 1
