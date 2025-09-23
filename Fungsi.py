"""Compatibility wrapper to keep legacy imports working."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from plastic_waste_detector import PlasticWasteDetector


class Deteksi(PlasticWasteDetector):
    """Backward-compatible alias for older scripts importing `Deteksi`."""

    def __init__(
        self,
        weights: str | Path,
        labels: Sequence[str],
        size: int = 640,
        confidence: float = 0.5,
        threshold: float = 0.3,
    ) -> None:  # pragma: no cover - thin wrapper
        super().__init__(weights, labels, size=size, confidence=confidence, threshold=threshold)
