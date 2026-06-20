"""Tests for src/plastic_waste_detector/detector.py.

All heavy ML dependencies (torch, cv2, PIL, torchvision, models, utils) are
stubbed out in conftest.py so these tests run on any host.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_detector(tmp_path, labels=None, **kwargs):
    """Create a PlasticWasteDetector with a dummy weights file and mocked model."""
    import src.plastic_waste_detector.detector as det_mod
    from src.plastic_waste_detector.detector import PlasticWasteDetector

    weights = tmp_path / "model.pt"
    weights.touch()
    if labels is None:
        labels = ["plastic bottle"]

    mock_model = MagicMock()
    with patch.object(det_mod, "attempt_load", return_value=mock_model):
        detector = PlasticWasteDetector(weights=str(weights), labels=labels, **kwargs)
    return detector


# ── init ─────────────────────────────────────────────────────────────────────

def test_missing_weights_raises():
    """FileNotFoundError is raised when the weights file does not exist."""
    from src.plastic_waste_detector.detector import PlasticWasteDetector

    with pytest.raises(FileNotFoundError, match="not found"):
        PlasticWasteDetector(weights="nonexistent.pt", labels=["plastic bottle"])


def test_init_default_params(tmp_path):
    """Default confidence / threshold / size are applied correctly."""
    detector = _make_detector(tmp_path, labels=["plastic bottle", "cable"])

    assert detector.labels == ["plastic bottle", "cable"]
    assert detector.confidence == 0.5
    assert detector.threshold == 0.3
    assert detector.size == 640


def test_init_custom_params(tmp_path):
    """Custom confidence / threshold / size are stored on the detector."""
    detector = _make_detector(
        tmp_path, labels=["a"], size=320, confidence=0.7, threshold=0.4
    )

    assert detector.size == 320
    assert detector.confidence == 0.7
    assert detector.threshold == 0.4


def test_init_calls_eval(tmp_path):
    """model.eval() is called once during initialisation."""
    import src.plastic_waste_detector.detector as det_mod
    from src.plastic_waste_detector.detector import PlasticWasteDetector

    weights = tmp_path / "model.pt"
    weights.touch()
    mock_model = MagicMock()
    with patch.object(det_mod, "attempt_load", return_value=mock_model):
        PlasticWasteDetector(weights=str(weights), labels=["plastic bottle"])

    mock_model.eval.assert_called_once()


# ── inference ─────────────────────────────────────────────────────────────────

def test_inference_no_detections_returns_empty_list(tmp_path):
    """inference() returns ([], float) when NMS produces no boxes."""
    import src.plastic_waste_detector.detector as det_mod

    # Make NMS signal "no detections"
    det_mod.non_max_suppression.return_value = [None]

    detector = _make_detector(tmp_path)

    frame = MagicMock()
    frame.shape = (480, 640, 3)

    detections, latency = detector.inference(frame)

    assert detections == []
    assert isinstance(latency, float)
    assert latency >= 0.0


def test_inference_latency_is_non_negative(tmp_path):
    """Returned latency value is always >= 0."""
    import src.plastic_waste_detector.detector as det_mod

    det_mod.non_max_suppression.return_value = [None]
    detector = _make_detector(tmp_path)

    frame = MagicMock()
    frame.shape = (480, 640, 3)
    _, latency = detector.inference(frame)

    assert latency >= 0.0


def test_call_delegates_to_inference(tmp_path):
    """__call__ produces the same result as calling inference() directly."""
    import src.plastic_waste_detector.detector as det_mod

    det_mod.non_max_suppression.return_value = [None]
    detector = _make_detector(tmp_path)

    frame = MagicMock()
    frame.shape = (480, 640, 3)

    result_call = detector(frame)
    result_inf = detector.inference(frame)

    # Both should return an empty detections list
    assert result_call[0] == result_inf[0] == []


# ── scale / clip helpers ──────────────────────────────────────────────────────

def test_clip_coords_calls_clamp():
    """clip_coords calls .clamp_() on the four coordinate columns."""
    from src.plastic_waste_detector.detector import clip_coords

    coords = MagicMock()
    clip_coords(coords, (480, 640, 3))

    # Four .clamp_() calls should have been made (x1, y1, x2, y2)
    assert coords.__getitem__.call_count >= 4


def test_scale_coords_returns_value():
    """scale_coords runs without error and returns a value."""
    from src.plastic_waste_detector.detector import scale_coords

    coords = MagicMock()
    result = scale_coords((640, 640), coords, (480, 640, 3))
    # With mocked tensors the return value is the mocked coords.round()
    assert result is not None
