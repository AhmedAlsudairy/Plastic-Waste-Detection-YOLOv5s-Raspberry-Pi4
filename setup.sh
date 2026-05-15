#!/usr/bin/env bash
# ================================================================
#  setup.sh — Run ONCE on your Raspberry Pi, then forget it.
#
#  What this does:
#    1. Installs all Python + system packages
#    2. On first boot (no WiFi saved): opens a hotspot called
#       "WasteDetector" — connect your phone, pick your WiFi,
#       enter password once. Done forever.
#    3. On every boot after that: auto-starts the detector.
#    4. No port number needed — just type the Pi's IP.
#
#  Usage:
#    chmod +x setup.sh
#    ./setup.sh
# ================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROVISION_SERVICE="wifi-provision"
DETECTOR_SERVICE="waste-detector"

echo ""
echo "  ♻  Plastic Waste Detector – One-time Setup"
echo "  ──────────────────────────────────────────"
echo ""

# ── Step 1 · System packages ──────────────────────────────────────────────
echo "▶ [1/5] Installing system packages …"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    python3-pip python3-opencv \
    libopenblas-dev \
    libjpeg-dev libopenjp2-7 \
    authbind dnsmasq-base \
    2>&1 | tail -5

# Allow the current user to bind port 80 without root (for detector UI)
DETECTOR_USER="${SUDO_USER:-$(whoami)}"
sudo touch /etc/authbind/byport/80
sudo chown "$DETECTOR_USER" /etc/authbind/byport/80
sudo chmod 500 /etc/authbind/byport/80

# ── Step 2 · Python packages ──────────────────────────────────────────────
echo "▶ [2/5] Installing Python packages …"
pip3 install --upgrade pip -q
pip3 install -r "$REPO_DIR/requirements.txt" -q
echo "      Done."

# ── Step 3 · NetworkManager – make sure wlan0 is managed ─────────────────
echo "▶ [3/5] Configuring NetworkManager …"
sudo systemctl enable NetworkManager 2>/dev/null || true
sudo systemctl start  NetworkManager 2>/dev/null || true
sudo nmcli device set wlan0 managed yes 2>/dev/null || true
sudo systemctl enable NetworkManager-wait-online.service 2>/dev/null || true

# ── Step 4 · WiFi provisioning service ───────────────────────────────────
echo "▶ [4/5] Installing WiFi provisioning service …"
sed "s|REPO_DIR_PLACEHOLDER|$REPO_DIR|g" \
    "$REPO_DIR/systemd/$PROVISION_SERVICE.service" \
    | sudo tee "/etc/systemd/system/$PROVISION_SERVICE.service" > /dev/null

# ── Step 5 · Detector service ─────────────────────────────────────────────
echo "▶ [5/5] Installing detector auto-start service …"
sed "s|REPO_DIR_PLACEHOLDER|$REPO_DIR|g" \
    "$REPO_DIR/systemd/$DETECTOR_SERVICE.service" \
    | sudo tee "/etc/systemd/system/$DETECTOR_SERVICE.service" > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable "$PROVISION_SERVICE"
sudo systemctl enable "$DETECTOR_SERVICE"

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
PI_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "  ✅  Setup complete! Reboot the Pi now:"
echo ""
echo "    sudo reboot"
echo ""
echo "  ┌──────────────────────────────────────────────────────────┐"
echo "  │  FIRST BOOT (no WiFi saved yet):                         │"
echo "  │    1. Connect your phone to WiFi: 'WasteDetector'        │"
echo "  │       Password: setup1234                                 │"
echo "  │    2. Open any browser — setup page opens automatically  │"
echo "  │    3. Pick your home WiFi, enter password, done!         │"
echo "  │                                                          │"
echo "  │  EVERY BOOT AFTER THAT:                                  │"
printf "  │    Open  http://%-41s│\n" "$PI_IP  "
echo "  │    (or http://raspberrypi.local)                         │"
echo "  └──────────────────────────────────────────────────────────┘"
echo ""
echo "  Useful commands:"
echo "    sudo systemctl status  $PROVISION_SERVICE"
echo "    sudo systemctl status  $DETECTOR_SERVICE"
echo "    sudo journalctl -u $DETECTOR_SERVICE -f    ← live logs"
echo ""
echo "    sudo journalctl -u $SERVICE -f    ← live logs"
echo ""
