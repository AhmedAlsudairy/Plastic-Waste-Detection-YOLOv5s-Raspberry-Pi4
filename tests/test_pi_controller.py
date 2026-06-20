"""Tests for src/plastic_waste_detector/pi_controller.py.

GPIO, LCD driver, and all ML deps are stubbed out by conftest.py.
"""
import threading
import time
from unittest.mock import MagicMock, call, patch

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_controller(**kwargs):
    """Return a WasteSorterController."""
    from src.plastic_waste_detector.pi_controller import WasteSorterController
    return WasteSorterController(**kwargs)


def _set_state_idle(ctrl):
    """Reset controller state to IDLE (for testing push_detection gate)."""
    ctrl.state = "IDLE"


# ── init / error paths ────────────────────────────────────────────────────────

def test_no_gpio_raises_runtime_error():
    """RuntimeError is raised when the GPIO library is unavailable."""
    import src.plastic_waste_detector.pi_controller as ctrl_mod
    from src.plastic_waste_detector.pi_controller import WasteSorterController

    with patch.object(ctrl_mod, "GPIO", None):
        with pytest.raises(RuntimeError, match="GPIO is unavailable"):
            WasteSorterController()


def test_init_stores_attributes():
    """WasteSorterController stores thresholds and timings."""
    from src.plastic_waste_detector.pi_controller import WasteSorterController
    controller = WasteSorterController(
        detection_threshold=10,
        collection_time=5.0,
        movement_timeout=20.0,
    )

    assert controller.detection_threshold == 10
    assert controller.collection_time == 5.0
    assert controller.movement_timeout == 20.0
    assert controller.state == "IDLE"


# ── push_detection ────────────────────────────────────────────────────────────

def test_push_detection_below_threshold_no_movement():
    """State stays IDLE until detection_threshold is reached."""
    controller = _make_controller(detection_threshold=5)

    for _ in range(4):
        controller.push_detection("plastic bottle")

    assert controller.state == "IDLE"


def test_push_detection_exceeds_threshold_triggers_movement():
    """State changes to MOVING once threshold exceeded."""
    controller = _make_controller(detection_threshold=2)

    for _ in range(3):
        controller.push_detection("plastic bottle")

    assert controller.state == "MOVING"


def test_push_detection_resets_count_after_trigger():
    """Count resets to 0 after threshold fires."""
    controller = _make_controller(detection_threshold=2)

    for _ in range(3):
        controller.push_detection("plastic bottle")

    # After trigger, counts for that label should be 0
    assert controller._counts.get("plastic bottle", 0) == 0


def test_push_detection_ignored_when_not_idle():
    """Detections are ignored when already MOVING or COLLECTING."""
    controller = _make_controller(detection_threshold=1)
    controller.state = "MOVING"

    controller.push_detection("plastic bottle")

    assert controller.state == "MOVING"


def test_push_detection_separate_class_counters():
    """Different class labels have independent counters."""
    controller = _make_controller(detection_threshold=3)

    for _ in range(3):
        controller.push_detection("plastic bottle")

    assert controller.state == "MOVING"
    assert controller._counts.get("plastic cup", 0) == 0


# ── Motor control ─────────────────────────────────────────────────────────────

def test_move_forward_sets_pins_correctly():
    """_move_forward sets IN1=L, IN2=H, IN3=L, IN4=H."""
    import RPi.GPIO as GPIO
    controller = _make_controller()

    controller._move_forward()

    GPIO.output.assert_has_calls([
        call(controller.IN1, GPIO.LOW),
        call(controller.IN2, GPIO.HIGH),
        call(controller.IN3, GPIO.LOW),
        call(controller.IN4, GPIO.HIGH),
    ], any_order=False)


def test_move_backward_sets_pins_correctly():
    """_move_backward sets IN1=H, IN2=L, IN3=H, IN4=L."""
    import RPi.GPIO as GPIO
    controller = _make_controller()

    controller._move_backward()

    GPIO.output.assert_has_calls([
        call(controller.IN1, GPIO.HIGH),
        call(controller.IN2, GPIO.LOW),
        call(controller.IN3, GPIO.HIGH),
        call(controller.IN4, GPIO.LOW),
    ], any_order=False)


def test_turn_right_sets_pins_correctly():
    """_turn_right sets IN1=L, IN2=H, IN3=H, IN4=L."""
    import RPi.GPIO as GPIO
    controller = _make_controller()

    controller._turn_right()

    GPIO.output.assert_has_calls([
        call(controller.IN1, GPIO.LOW),
        call(controller.IN2, GPIO.HIGH),
        call(controller.IN3, GPIO.HIGH),
        call(controller.IN4, GPIO.LOW),
    ], any_order=False)


def test_turn_left_sets_pins_correctly():
    """_turn_left sets IN1=H, IN2=L, IN3=L, IN4=H."""
    import RPi.GPIO as GPIO
    controller = _make_controller()

    controller._turn_left()

    GPIO.output.assert_has_calls([
        call(controller.IN1, GPIO.HIGH),
        call(controller.IN2, GPIO.LOW),
        call(controller.IN3, GPIO.LOW),
        call(controller.IN4, GPIO.HIGH),
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

def test_process_moving_state_timeout_returns_to_idle():
    """_process_moving_state resets to IDLE when movement_timeout exceeded."""
    controller = _make_controller(movement_timeout=0.001)
    controller.state = "MOVING"
    controller._move_start = 0.0

    controller._process_moving_state()

    assert controller.state == "IDLE"


def test_process_moving_state_ir_obstacle_detected():
    """_process_moving_state stops motors, fires relay, resets to IDLE."""
    import RPi.GPIO as GPIO
    controller = _make_controller(collection_time=0.01)
    controller.state = "MOVING"
    controller._move_start = time.perf_counter()
    GPIO.input.return_value = GPIO.LOW

    with patch("src.plastic_waste_detector.pi_controller.time.sleep"):
        controller._process_moving_state()

    assert controller.state == "IDLE"
    GPIO.output.assert_any_call(controller.RELAY_PIN, GPIO.LOW)


def test_process_moving_state_no_obstacle_stays_moving():
    """_process_moving_state stays MOVING when IR sees no obstacle."""
    import RPi.GPIO as GPIO
    controller = _make_controller(movement_timeout=30)
    controller.state = "MOVING"
    controller._move_start = time.perf_counter()
    GPIO.input.return_value = GPIO.HIGH

    controller._process_moving_state()

    assert controller.state == "MOVING"


# ── Thread safety ─────────────────────────────────────────────────────────────

def test_push_detection_is_thread_safe():
    """push_detection works correctly from multiple threads."""
    controller = _make_controller(detection_threshold=5)

    def pusher():
        for _ in range(6):
            controller.push_detection("plastic bottle")

    threads = [threading.Thread(target=pusher) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # At least one thread should have triggered MOVING state
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
