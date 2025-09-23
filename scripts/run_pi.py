#!/usr/bin/env python3
"""Launch the Raspberry Pi waste sorter runtime."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from plastic_waste_detector import WasteSorterController, build_detector  # noqa: E402


def main() -> None:
    weights = ROOT / "best.pt"
    data_yaml = ROOT / "data.yaml"

    detector = build_detector(weights, data_yaml)
    controller = WasteSorterController(detector=detector, classes=detector.labels)
    controller.run()


if __name__ == "__main__":
    main()
