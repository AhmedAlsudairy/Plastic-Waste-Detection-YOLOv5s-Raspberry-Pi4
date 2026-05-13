#!/usr/bin/env bash
# ============================================================
#  install_pi.sh – One-shot setup for Raspberry Pi 4
#  Run as the 'pi' user with sudo access.
#
#  Usage:
#    chmod +x install_pi.sh
#    ./install_pi.sh
# ============================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="waste-detector"
SERVICE_SRC="$REPO_DIR/systemd/$SERVICE_NAME.service"
SERVICE_DEST="/etc/systemd/system/$SERVICE_NAME.service"

echo "========================================================"
echo "  Plastic Waste Detector – Pi 4 Install"
echo "  Project dir: $REPO_DIR"
echo "========================================================"

# ── 1. System packages ────────────────────────────────────────────────────
echo ""
echo "[1/5] Installing system dependencies …"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    python3-pip \
    python3-opencv \
    libopenblas-dev \
    libatlas-base-dev \
    libjpeg-dev \
    libopenjp2-7

# ── 2. Python packages ────────────────────────────────────────────────────
echo ""
echo "[2/5] Installing Python packages …"
pip3 install --upgrade pip --quiet
pip3 install -r "$REPO_DIR/requirements.txt" --quiet

# ── 3. Enable camera (legacy camera stack for OpenCV) ─────────────────────
echo ""
echo "[3/5] Ensuring camera interface is enabled …"
if ! grep -q "^start_x=1" /boot/config.txt 2>/dev/null; then
    echo "      Adding start_x=1 to /boot/config.txt"
    echo "start_x=1" | sudo tee -a /boot/config.txt > /dev/null
else
    echo "      Camera already enabled in /boot/config.txt"
fi

# ── 4. Systemd service ────────────────────────────────────────────────────
echo ""
echo "[4/5] Installing systemd service …"
# Patch WorkingDirectory / ExecStart to match actual location
sed "s|/home/pi/plastic-waste-detector|$REPO_DIR|g" "$SERVICE_SRC" \
    | sudo tee "$SERVICE_DEST" > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

# ── 5. Done ──────────────────────────────────────────────────────────────
echo ""
echo "[5/5] Done!"
echo ""
PI_IP=$(hostname -I | awk '{print $1}')
echo "========================================================"
echo "  Access the web UI at:"
echo "    http://$PI_IP:5000"
echo ""
echo "  Service commands:"
echo "    sudo systemctl status  $SERVICE_NAME"
echo "    sudo systemctl restart $SERVICE_NAME"
echo "    sudo journalctl -u $SERVICE_NAME -f   (live logs)"
echo "========================================================"
