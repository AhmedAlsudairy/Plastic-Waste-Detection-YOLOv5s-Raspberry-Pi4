#!/usr/bin/env python3
"""wifi_setup.py — One-time WiFi provisioning captive portal.

Boot flow
─────────
1.  If Pi already has internet → exit immediately (nothing to do).
2.  Scan nearby networks, then start a hotspot called "WasteDetector".
3.  Serve a web portal on port 80 of the hotspot IP.
4.  User connects phone/laptop to "WasteDetector", opens any browser.
5.  Portal shows scanned networks; user picks theirs + enters password.
6.  Pi connects to home WiFi, hotspot shuts down, this script exits.
7.  waste-detector.service starts automatically.

Run as root (required for nmcli hotspot + dnsmasq config).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flask import Flask, jsonify, redirect, render_template, request

# ── Config ────────────────────────────────────────────────────────────────────
AP_SSID      = "WasteDetector"
AP_PASSWORD  = "setup1234"
AP_CON_NAME  = "WasteDetector-AP"
IFACE        = "wlan0"
DNSMASQ_CONF = "/etc/NetworkManager/dnsmasq-shared.d/captive-portal.conf"
PORTAL_PORT  = 80

# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout
    )


def is_connected() -> bool:
    r = _run("nmcli -t -f CONNECTIVITY general")
    return "full" in r.stdout.lower()


def get_hotspot_ip() -> str:
    """Return the IP assigned to wlan0 when acting as AP (usually 10.42.0.1)."""
    r = _run(f"nmcli -t -f IP4.ADDRESS device show {IFACE}")
    for line in r.stdout.splitlines():
        if "IP4.ADDRESS" in line:
            addr = line.split(":")[-1].split("/")[0].strip()
            if addr and not addr.startswith("169."):
                return addr
    return "10.42.0.1"


def scan_networks() -> list[dict]:
    """Return list of nearby WiFi networks (excludes own AP)."""
    _run(f"nmcli device wifi rescan ifname {IFACE}", timeout=10)
    time.sleep(3)
    r = _run(f"nmcli -t -f SSID,SIGNAL,SECURITY device wifi list ifname {IFACE}")
    seen: set[str] = set()
    nets: list[dict] = []
    for line in r.stdout.strip().splitlines():
        parts = line.split(":")
        if len(parts) < 2:
            continue
        ssid = parts[0].strip()
        if not ssid or ssid == AP_SSID or ssid in seen:
            continue
        seen.add(ssid)
        try:
            signal = int(parts[1])
        except (ValueError, IndexError):
            signal = 0
        security = parts[2].strip() if len(parts) > 2 else ""
        nets.append({"ssid": ssid, "signal": signal, "secure": bool(security)})
    nets.sort(key=lambda x: x["signal"], reverse=True)
    return nets


def start_hotspot() -> bool:
    _run(f"nmcli connection delete '{AP_CON_NAME}' 2>/dev/null || true")
    r = _run(
        f"nmcli device wifi hotspot ifname {IFACE} "
        f"con-name '{AP_CON_NAME}' ssid '{AP_SSID}' password '{AP_PASSWORD}'",
        timeout=20,
    )
    if r.returncode != 0:
        print(f"[wifi-setup] hotspot error: {r.stderr.strip()}")
        return False
    return True


def stop_hotspot() -> None:
    _run(f"nmcli connection down '{AP_CON_NAME}' 2>/dev/null || true")
    _run(f"nmcli connection delete '{AP_CON_NAME}' 2>/dev/null || true")


def install_dns_redirect(ap_ip: str) -> None:
    """Make every domain resolve to the portal so captive-portal dialogs open."""
    os.makedirs(os.path.dirname(DNSMASQ_CONF), exist_ok=True)
    with open(DNSMASQ_CONF, "w") as f:
        f.write(f"address=/#/{ap_ip}\n")
    _run("systemctl reload NetworkManager 2>/dev/null || true")


def remove_dns_redirect() -> None:
    try:
        os.remove(DNSMASQ_CONF)
    except FileNotFoundError:
        pass
    _run("systemctl reload NetworkManager 2>/dev/null || true")


def connect_to_wifi(ssid: str, password: str) -> tuple[bool, str]:
    """Stop hotspot and connect to the given network. Returns (success, ip)."""
    stop_hotspot()
    remove_dns_redirect()
    time.sleep(2)

    cmd = f"nmcli device wifi connect '{ssid}' ifname {IFACE}"
    if password:
        cmd += f" password '{password}'"
    r = _run(cmd, timeout=40)

    if r.returncode != 0:
        print(f"[wifi-setup] connect error: {r.stderr.strip()}")
        return False, ""

    # Wait for IP
    for _ in range(15):
        time.sleep(2)
        r2 = _run(f"nmcli -t -f IP4.ADDRESS device show {IFACE}")
        for line in r2.stdout.splitlines():
            if "IP4.ADDRESS" in line:
                ip = line.split(":")[-1].split("/")[0].strip()
                if ip and not ip.startswith("169."):
                    return True, ip
    return False, ""


# ── Shared connect state ──────────────────────────────────────────────────────
_connect_state: dict = {"status": "idle", "ip": "", "error": ""}
_shutdown_event = threading.Event()

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
_cached_networks: list[dict] = []


@app.route("/")
@app.route("/index.html")
def index():
    return render_template("portal.html", networks=_cached_networks, ap_ssid=AP_SSID)


# Captive portal detection endpoints (iOS / Android / Windows auto-open)
@app.route("/hotspot-detect.html")
@app.route("/library/test/success.html")
@app.route("/generate_204")
@app.route("/ncsi.txt")
@app.route("/connecttest.txt")
@app.route("/redirect")
@app.route("/canonical.html")
def captive_redirect():
    return redirect("/", 302)


@app.route("/api/networks")
def api_networks():
    return jsonify(_cached_networks)


@app.route("/api/connect", methods=["POST"])
def api_connect():
    global _connect_state
    if _connect_state["status"] == "connecting":
        return jsonify({"status": "connecting"})

    data = request.get_json(force=True) or {}
    ssid = (data.get("ssid") or "").strip()
    password = (data.get("password") or "").strip()

    if not ssid:
        return jsonify({"status": "error", "error": "No network selected."}), 400

    _connect_state = {"status": "connecting", "ip": "", "error": ""}

    def _worker():
        ok, ip = connect_to_wifi(ssid, password)
        if ok:
            _connect_state.update({"status": "connected", "ip": ip})
            _shutdown_event.set()
        else:
            _connect_state.update({"status": "error", "error": "Wrong password or network unreachable."})
            # Re-start hotspot so user can try again
            start_hotspot()
            install_dns_redirect(get_hotspot_ip())

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "connecting", "ssid": ssid})


@app.route("/api/status")
def api_status():
    return jsonify(_connect_state)


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    global _cached_networks

    if is_connected():
        print("[wifi-setup] Already connected — nothing to do.")
        sys.exit(0)

    # Scan before starting AP (wlan0 must be in station mode)
    print("[wifi-setup] Scanning for networks …")
    _cached_networks = scan_networks()
    print(f"[wifi-setup] Found {len(_cached_networks)} network(s).")

    print(f"[wifi-setup] Starting hotspot '{AP_SSID}' …")
    if not start_hotspot():
        print("[wifi-setup] ERROR: Could not start hotspot. Exiting.")
        sys.exit(1)

    time.sleep(3)  # Let NM settle
    ap_ip = get_hotspot_ip()
    print(f"[wifi-setup] Hotspot IP: {ap_ip}")

    install_dns_redirect(ap_ip)

    print(f"[wifi-setup] Portal at http://{ap_ip}")
    print(f"[wifi-setup] Connect to WiFi '{AP_SSID}' (password: {AP_PASSWORD}), then open any browser.")

    # Run Flask in a daemon thread
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=PORTAL_PORT, debug=False, use_reloader=False),
        daemon=True,
    )
    flask_thread.start()

    # Block until successfully connected
    _shutdown_event.wait()
    time.sleep(2)

    print(f"[wifi-setup] Connected! Pi IP: {_connect_state.get('ip', '?')}")
    print("[wifi-setup] WiFi provisioning complete. Detector will start now.")
    sys.exit(0)


if __name__ == "__main__":
    main()
