# Run browser after boot to desktop
/bin/sleep 3
# --- historial (por si hay que volver a Dakboard) ---
#sudo -u pi chromium-browser --kiosk --incognito http://localhost/index.html &
#sudo -u pi chromium-browser --kiosk --incognito https://dakboard.com/screen/uuid/62153e14-11bcf3-101e-dcca53cb9f18 &
# sudo -u pi chromium-browser --kiosk --incognito https://dakboard.com/screen/uuid/6402460d-11bcf3-24ae-ec1f2e404c1d &
#sudo -u pi chromium-browser --kiosk --incognito https://dakboard.com/loop/uuid/6520730c-11bcf3-2d28-8e4c31aa4446 &
#sudo -u pi chromium-browser --kiosk --incognito https://dakboard.com/screen/uuid/64449785-11bcf3-0a91-0338131f2b4e &
#sudo -u pi chromium-browser --kiosk --incognito https://dakboard.com/screen/uuid/67e80379-11bcf3-b993-f8b81cbd41a5 &
#sudo -u pi chromium-browser --kiosk --incognito https://dakboard.com/screen/uuid/6ad8c83c-11bcf3-9f85-c93d2d6ce508 &
# --- Monitor: tablero propio, servido por esta misma Pi (systemd --user monitor) ---
# --password-store=basic: sin llavero de GNOME, que en un kiosco sólo saca el
#   diálogo "Choose password for new keyring" encima de la pantalla.
# sin --incognito: así recuerda si estaba en paleta día o noche y no parpadea en
#   blanco al arrancar de madrugada.
sudo -u pi chromium-browser --kiosk --noerrdialogs --disable-infobars \
  --disable-session-crashed-bubble --overscroll-history-navigation=0 \
  --check-for-update-interval=31536000 --password-store=basic \
  http://localhost:8770/ &
# End of script
