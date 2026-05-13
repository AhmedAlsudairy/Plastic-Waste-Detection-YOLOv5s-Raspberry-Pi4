#!/usr/bin/env bash
# ================================================================
#  setup.sh — Run ONCE on your Raspberry Pi, then forget it.
#
#  What this does:
#    1. Installs all Python packages
#    2. Makes the detector start automatically on every boot
#    3. Makes it wait for WiFi before starting
#    4. Prints your access URL when done
#
#  Usage:
#    chmod +x setup.sh
#    ./setup.sh
# ================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="waste-detector"
SERVICE_FILE="/etc/systemd/system/$SERVICE.service"

echo ""
echo "  ♻  Plastic Waste Detector – One-time Setup"
echo "  ──────────────────────────────────────────"
echo ""

# ── Step 1 · System packages ──────────────────────────────────────────────
echo "▶ [1/4] Installing system packages …"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    python3-pip python3-opencv \
    libopenblas-dev libatlas-base-dev \
    libjpeg-dev libopenjp2-7 \
    authbind \
    2>&1 | tail -5

# Allow the 'pi' user to bind port 80 without root
sudo touch /etc/authbind/byport/80
sudo chown pi /etc/authbind/byport/80
sudo chmod 500 /etc/authbind/byport/80

# ── Step 2 · Python packages ──────────────────────────────────────────────
echo "▶ [2/4] Installing Python packages …"
pip3 install --upgrade pip -q
pip3 install -r "$REPO_DIR/requirements.txt" -q
echo "      Done."

# ── Step 3 · Enable network-online.target (makes WiFi-wait work) ──────────
echo "▶ [3/4] Enabling network wait service …"
# Works for both NetworkManager (Bookworm) and dhcpcd (Bullseye)
sudo systemctl enable NetworkManager-wait-online.service 2>/dev/null || true
sudo systemctl enable systemd-networkd-wait-online.service 2>/dev/null || true

# ── Step 4 · Install & enable the systemd service ─────────────────────────
echo "▶ [4/4] Setting up auto-start service …"
# Patch the placeholder path to the real project directory
sed "s|REPO_DIR_PLACEHOLDER|$REPO_DIR|g" \
    "$REPO_DIR/systemd/$SERVICE.service" \
    | sudo tee "$SERVICE_FILE" > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE"
sudo systemctl restart "$SERVICE"

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
PI_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "  ✅  Setup complete!"
echo ""
echo "  ┌─────────────────────────────────────────────┐"
echo "  │  Open this in any browser on your network:  │"
echo "  │                                              │"
printf "  │    http://%-34s │\n" "$PI_IP"
echo "  │                                              │"
echo "  │  No port number needed — just the IP.        │"
echo "  │  Starts automatically on every WiFi connect. │"
echo "  └─────────────────────────────────────────────┘"
echo ""
echo "  Useful commands (if you ever need them):"
echo "    sudo systemctl status  $SERVICE"
echo "    sudo systemctl restart $SERVICE"
echo "    sudo journalctl -u $SERVICE -f    ← live logs"
echo ""
