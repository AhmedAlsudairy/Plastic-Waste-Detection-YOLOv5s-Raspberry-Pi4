#!/usr/bin/env python3
"""Quick GPIO motor test — moves forward 3s, backward 3s, then stops.

For full waste-detection + movement, run:  python3 app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import time


def main() -> None:
    from plastic_waste_detector.pi_controller import WasteSorterController

    ctrl = WasteSorterController(detection_threshold=3)
    ctrl.setup()
    print("[TEST] Moving forward 3s ...")
    ctrl._move_forward()
    time.sleep(3)
    print("[TEST] Moving backward 3s ...")
    ctrl._move_backward()
    time.sleep(3)
    print("[TEST] Stop")
    ctrl._stop_motors()
    ctrl._deactivate_relay()
    from RPi import GPIO
    GPIO.cleanup()
    print("[TEST] Done")


if __name__ == "__main__":
    main()
