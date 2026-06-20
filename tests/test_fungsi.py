"""Tests for Fungsi.py – the backward-compatibility wrapper."""
from unittest.mock import MagicMock, patch


# ── class hierarchy ───────────────────────────────────────────────────────────

def test_deteksi_is_subclass_of_plastic_waste_detector():
    """Deteksi must inherit from PlasticWasteDetector."""
    from Fungsi import Deteksi
    from plastic_waste_detector.detector import PlasticWasteDetector

    assert issubclass(Deteksi, PlasticWasteDetector)


def test_deteksi_docstring_mentions_alias():
    """Deteksi docstring should describe it as a backward-compatible alias."""
    from Fungsi import Deteksi

    assert Deteksi.__doc__ is not None
    assert "alias" in Deteksi.__doc__.lower()


# ── instantiation ─────────────────────────────────────────────────────────────

def test_deteksi_instantiation_passes_args_to_parent(tmp_path):
    """Deteksi forwards all constructor arguments to PlasticWasteDetector."""
    import src.plastic_waste_detector.detector as det_mod
    from Fungsi import Deteksi

    weights = tmp_path / "model.pt"
    weights.touch()

    with patch.object(det_mod, "attempt_load", return_value=MagicMock()):
        d = Deteksi(
            weights=str(weights),
            labels=["plastic bottle"],
            size=320,
            confidence=0.6,
            threshold=0.35,
        )

    assert d.labels == ["plastic bottle"]
    assert d.size == 320
    assert d.confidence == 0.6
    assert d.threshold == 0.35
