"""Tests for src/plastic_waste_detector/pi_controller.py.

GPIO, LCD driver, and all ML deps are stubbed out by conftest.py.
"""
from unittest.mock import MagicMock, call, patch

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_controller(detector=None, classes=None, **kwargs):
    """Return a WasteSorterController with display fully mocked."""
    from src.plastic_waste_detector.pi_controller import WasteSorterController

    if detector is None:
        detector = MagicMock()
        detector.labels = classes or ["plastic bottle"]
    if classes is None:
        classes = ["plastic bottle"]

    with patch("src.plastic_waste_detector.pi_controller.drivers") as mock_drv:
        controller = WasteSorterController(
            detector=detector, classes=classes, **kwargs
        )
    return controller


# ── init / error paths ────────────────────────────────────────────────────────

def test_no_gpio_raises_runtime_error():
    """RuntimeError is raised when the GPIO library is unavailable."""
    import src.plastic_waste_detector.pi_controller as ctrl_mod
    from src.plastic_waste_detector.pi_controller import WasteSorterController

    with patch.object(ctrl_mod, "GPIO", None), patch.object(ctrl_mod, "drivers", None):
        with pytest.raises(RuntimeError, match="GPIO or LCD drivers"):
            WasteSorterController(MagicMock(), ["plastic bottle"])


def test_init_stores_attributes():
    """WasteSorterController stores detector, classes, thresholds."""
    detector = MagicMock()
    detector.labels = ["plastic bottle"]

    with patch("src.plastic_waste_detector.pi_controller.drivers"):
        from src.plastic_waste_detector.pi_controller import WasteSorterController
        controller = WasteSorterController(
            detector=detector,
            classes=["plastic bottle", "cable"],
            capture_index=2,
            detection_threshold=10,
            collection_time=5.0,
        )

    assert controller.detector is detector
    assert controller.classes == ["plastic bottle", "cable"]
    assert controller.capture_index == 2
    assert controller.detection_threshold == 10
    assert controller.collection_time == 5.0
    assert controller.state == "IDLE"


def test_init_label_map_defined():
    """All six plastic categories have label_map entries."""
    controller = _make_controller()

    expected = {"plastic bottle", "plastic cup", "soap bottle", "cable", "sterofoam", "plastic bag"}
    assert set(controller.label_map.keys()) == expected


# ── _handle_detection ─────────────────────────────────────────────────────────

def test_handle_detection_below_threshold_no_action():
    """No LCD / motor activity until detection_threshold is reached."""
    controller = _make_controller(detection_threshold=5)
    controller.display = MagicMock()

    counts = {"plastic bottle": 0}
    detection = {"class_id": 0, "confidence": 0.9, "box": [0, 0, 100, 100]}

    for _ in range(4):
        controller._handle_detection(detection, counts, 0.05)

    controller.display.lcd_display_string.assert_not_called()
    assert controller.state == "IDLE"


def test_handle_detection_exceeds_threshold_triggers_movement():
    """LCD shows detection and state changes to MOVING once threshold exceeded."""
    controller = _make_controller(detection_threshold=2)
    controller.display = MagicMock()

    counts = {"plastic bottle": 0}
    detection = {"class_id": 0, "confidence": 0.9, "box": [0, 0, 100, 100]}

    with patch("src.plastic_waste_detector.pi_controller.time.sleep"):
        for _ in range(3):
            controller._handle_detection(detection, counts, 0.05)

    controller.display.lcd_display_string.assert_called()
    assert controller.state == "MOVING"


def test_handle_detection_resets_count_after_action():
    """Count for a label is reset to 0 after threshold is reached."""
    controller = _make_controller(detection_threshold=2)
    controller.display = MagicMock()

    counts = {"plastic bottle": 0}
    detection = {"class_id": 0, "confidence": 0.9, "box": [0, 0, 100, 100]}

    with patch("src.plastic_waste_detector.pi_controller.time.sleep"):
        for _ in range(3):
            controller._handle_detection(detection, counts, 0.05)

    assert counts["plastic bottle"] == 0


def test_handle_detection_unknown_label_no_crash():
    """Unknown class_id does not raise an exception."""
    controller = _make_controller(detection_threshold=1)
    controller.detector.labels = ["unknown_waste"]
    controller.display = MagicMock()

    counts = {}
    detection = {"class_id": 0, "confidence": 0.8, "box": [0, 0, 50, 50]}

    with patch("src.plastic_waste_detector.pi_controller.time.sleep"):
        controller._handle_detection(detection, counts, 0.03)


# ── Motor control ─────────────────────────────────────────────────────────────

def test_move_forward_sets_pins_correctly():
    """_move_forward sets IN1=H, IN2=L, IN3=H, IN4=L."""
    import RPi.GPIO as GPIO
    controller = _make_controller()

    controller._move_forward()

    GPIO.output.assert_has_calls([
        call(controller.IN1, GPIO.HIGH),
        call(controller.IN2, GPIO.LOW),
        call(controller.IN3, GPIO.HIGH),
        call(controller.IN4, GPIO.LOW),
    ], any_order=False)


def test_move_backward_sets_pins_correctly():
    """_move_backward sets IN1=L, IN2=H, IN3=L, IN4=H."""
    import RPi.GPIO as GPIO
    controller = _make_controller()

    controller._move_backward()

    GPIO.output.assert_has_calls([
        call(controller.IN1, GPIO.LOW),
        call(controller.IN2, GPIO.HIGH),
        call(controller.IN3, GPIO.LOW),
        call(controller.IN4, GPIO.HIGH),
    ], any_order=False)


def test_turn_right_sets_pins_correctly():
    """_turn_right sets IN1=H, IN2=L, IN3=L, IN4=H."""
    import RPi.GPIO as GPIO
    controller = _make_controller()

    controller._turn_right()

    GPIO.output.assert_has_calls([
        call(controller.IN1, GPIO.HIGH),
        call(controller.IN2, GPIO.LOW),
        call(controller.IN3, GPIO.LOW),
        call(controller.IN4, GPIO.HIGH),
    ], any_order=False)


def test_turn_left_sets_pins_correctly():
    """_turn_left sets IN1=L, IN2=H, IN3=H, IN4=L."""
    import RPi.GPIO as GPIO
    controller = _make_controller()

    controller._turn_left()

    GPIO.output.assert_has_calls([
        call(controller.IN1, GPIO.LOW),
        call(controller.IN2, GPIO.HIGH),
        call(controller.IN3, GPIO.HIGH),
        call(controller.IN4, GPIO.LOW),
    ], any_order=False)


def test_stop_motors_sets_all_pins_low():
    """_stop_motors sets all four motor pins LOW."""
    import RPi.GPIO as GPIO
    controller = _make_controller()

    controller._stop_motors()

    GPIO.output.assert_has_calls([
        call(controller.IN1, GPIO.LOW),
        call(controller.IN2, GPIO.LOW),
        call(controller.IN3, GPIO.LOW),
        call(controller.IN4, GPIO.LOW),
    ], any_order=False)


# ── Relay control ─────────────────────────────────────────────────────────────

def test_activate_relay_sets_low():
    """_activate_relay sets RELAY_PIN LOW."""
    import RPi.GPIO as GPIO
    controller = _make_controller()

    controller._activate_relay()

    GPIO.output.assert_called_with(controller.RELAY_PIN, GPIO.LOW)


def test_deactivate_relay_sets_high():
    """_deactivate_relay sets RELAY_PIN HIGH."""
    import RPi.GPIO as GPIO
    controller = _make_controller()

    controller._deactivate_relay()

    GPIO.output.assert_called_with(controller.RELAY_PIN, GPIO.HIGH)


# ── State machine ─────────────────────────────────────────────────────────────

def test_process_moving_state_ir_obstacle_detected():
    """_process_moving_state stops motors, fires relay, resets to IDLE."""
    import RPi.GPIO as GPIO
    controller = _make_controller(collection_time=0.01)
    controller.display = MagicMock()
    controller.state = "MOVING"
    GPIO.input.return_value = GPIO.LOW

    with patch("src.plastic_waste_detector.pi_controller.time.sleep"):
        controller._process_moving_state()

    assert controller.state == "IDLE"
    GPIO.output.assert_any_call(controller.RELAY_PIN, GPIO.LOW)


def test_process_moving_state_no_obstacle_stays_moving():
    """_process_moving_state stays MOVING when IR sees no obstacle."""
    import RPi.GPIO as GPIO
    controller = _make_controller()
    controller.display = MagicMock()
    controller.state = "MOVING"
    GPIO.input.return_value = GPIO.HIGH  # no obstacle

    with patch("src.plastic_waste_detector.pi_controller.time.sleep"):
        controller._process_moving_state()

    assert controller.state == "MOVING"


# ── build_detector ────────────────────────────────────────────────────────────

def test_build_detector_reads_yaml_and_creates_detector(tmp_path):
    """build_detector parses data.yaml names and returns a PlasticWasteDetector."""
    import yaml
    import src.plastic_waste_detector.detector as det_mod
    from src.plastic_waste_detector.pi_controller import build_detector

    data_yaml = tmp_path / "data.yaml"
    weights = tmp_path / "model.pt"
    weights.touch()
    data_yaml.write_text(yaml.dump({"names": ["plastic bottle", "cable"]}))

    with patch.object(det_mod, "attempt_load", return_value=MagicMock()):
        detector = build_detector(str(weights), str(data_yaml))

    assert detector.labels == ["plastic bottle", "cable"]


def test_build_detector_missing_names_gives_empty_labels(tmp_path):
    """build_detector returns an empty labels list when names is absent."""
    import yaml
    import src.plastic_waste_detector.detector as det_mod
    from src.plastic_waste_detector.pi_controller import build_detector

    data_yaml = tmp_path / "data.yaml"
    weights = tmp_path / "model.pt"
    weights.touch()
    data_yaml.write_text(yaml.dump({}))

    with patch.object(det_mod, "attempt_load", return_value=MagicMock()):
        detector = build_detector(str(weights), str(data_yaml))

    assert detector.labels == []
