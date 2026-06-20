"""Runtime control loop for the Raspberry Pi deployment."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, MutableMapping

import time
import yaml

import cv2

try:  # pragma: no cover - hardware dependency
    import RPi.GPIO as GPIO
except ModuleNotFoundError:  # pragma: no cover - allows development on non-Pi hosts
    GPIO = None  # type: ignore

try:  # pragma: no cover - hardware dependency
    import drivers  # LCD driver used on the Pi
except ModuleNotFoundError:  # pragma: no cover
    drivers = None  # type: ignore

from .detector import PlasticWasteDetector


class WasteSorterController:
    """Encapsulates GPIO, LCD, motors, relay and detection loop for the sorter."""

    IR_PIN = 18
    RELAY_PIN = 14
    IN1 = 8
    IN2 = 7
    IN3 = 16
    IN4 = 20

    def __init__(
        self,
        detector: PlasticWasteDetector,
        classes: Iterable[str],
        capture_index: int = 0,
        detection_threshold: int = 5,
        collection_time: float = 3.0,
    ) -> None:
        if GPIO is None or drivers is None:
            raise RuntimeError(
                "GPIO or LCD drivers are unavailable. Run on Raspberry Pi with required libraries installed"
            )

        self.detector = detector
        self.classes = list(classes)
        self.capture_index = capture_index
        self.detection_threshold = detection_threshold
        self.collection_time = collection_time

        self.display = drivers.Lcd()
        self.state = "IDLE"

        self.label_map: Dict[str, str] = {
            "plastic bottle": "PET",
            "plastic cup": "PP",
            "soap bottle": "HDPE",
            "cable": "PVC",
            "sterofoam": "PS",
            "plastic bag": "LDPE",
        }

    def setup(self) -> None:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        self.display.lcd_clear()
        self.display.lcd_display_string("STAND", 1)
        self.display.lcd_display_string("BY", 2)

        GPIO.setup(self.IR_PIN, GPIO.IN)
        GPIO.setup(self.RELAY_PIN, GPIO.OUT, initial=GPIO.HIGH)

        for pin in (self.IN1, self.IN2, self.IN3, self.IN4):
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

        self.display.lcd_clear()
        self.display.lcd_display_string("MENYALAKAN", 1)
        self.display.lcd_display_string("KAMERA", 2)
        time.sleep(2)
        self.display.lcd_clear()

    def run(self) -> None:
        self.setup()
        capture = cv2.VideoCapture(self.capture_index)
        counts = {name: 0 for name in self.classes}

        try:
            while True:
                ret, frame = capture.read()
                if not ret:
                    continue

                frame = cv2.flip(frame, 1)

                if self.state == "IDLE":
                    detections, latency = self.detector.inference(frame)
                    for detection in detections:
                        self._handle_detection(detection, counts, latency)
                elif self.state == "MOVING":
                    self._process_moving_state()

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        finally:
            capture.release()
            cv2.destroyAllWindows()
            self._stop_motors()
            GPIO.cleanup()

    def _handle_detection(
        self,
        detection: MutableMapping[str, float | int | List[float]],
        counts: Dict[str, int],
        latency: float,
    ) -> None:
        class_id = int(detection["class_id"])
        label = self.detector.labels[class_id]
        counts[label] = counts.get(label, 0) + 1

        if counts[label] <= self.detection_threshold:
            return

        counts[label] = 0
        short_label = self.label_map.get(label, label.upper())
        self.display.lcd_clear()
        self.display.lcd_display_string(short_label, 1)
        self.display.lcd_display_string("TERDETEKSI", 2)
        time.sleep(1)
        self.display.lcd_clear()
        self.display.lcd_display_string("-MENDEXATI-", 1)

        self._move_forward()
        self.state = "MOVING"

    # ── State machine helpers ──────────────────────────────────────────────

    def _process_moving_state(self) -> None:
        """Check IR sensor while moving; transition to COLLECTING on obstacle."""
        if GPIO.input(self.IR_PIN) == GPIO.LOW:
            self._stop_motors()
            self._activate_relay()
            self.display.lcd_clear()
            self.display.lcd_display_string("MENGUMPULKAN", 1)
            self.state = "COLLECTING"
            time.sleep(self.collection_time)
            self._deactivate_relay()
            self.display.lcd_clear()
            self.state = "IDLE"

    # ── Motor control ──────────────────────────────────────────────────────

    def _move_forward(self) -> None:
        GPIO.output(self.IN1, GPIO.HIGH)
        GPIO.output(self.IN2, GPIO.LOW)
        GPIO.output(self.IN3, GPIO.HIGH)
        GPIO.output(self.IN4, GPIO.LOW)

    def _move_backward(self) -> None:
        GPIO.output(self.IN1, GPIO.LOW)
        GPIO.output(self.IN2, GPIO.HIGH)
        GPIO.output(self.IN3, GPIO.LOW)
        GPIO.output(self.IN4, GPIO.HIGH)

    def _turn_right(self) -> None:
        GPIO.output(self.IN1, GPIO.HIGH)
        GPIO.output(self.IN2, GPIO.LOW)
        GPIO.output(self.IN3, GPIO.LOW)
        GPIO.output(self.IN4, GPIO.HIGH)

    def _turn_left(self) -> None:
        GPIO.output(self.IN1, GPIO.LOW)
        GPIO.output(self.IN2, GPIO.HIGH)
        GPIO.output(self.IN3, GPIO.HIGH)
        GPIO.output(self.IN4, GPIO.LOW)

    def _stop_motors(self) -> None:
        GPIO.output(self.IN1, GPIO.LOW)
        GPIO.output(self.IN2, GPIO.LOW)
        GPIO.output(self.IN3, GPIO.LOW)
        GPIO.output(self.IN4, GPIO.LOW)

    # ── Relay control ──────────────────────────────────────────────────────

    def _activate_relay(self) -> None:
        GPIO.output(self.RELAY_PIN, GPIO.LOW)

    def _deactivate_relay(self) -> None:
        GPIO.output(self.RELAY_PIN, GPIO.HIGH)


def build_detector(weights_path: Path | str, data_yaml: Path | str) -> PlasticWasteDetector:
    with open(data_yaml, "r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    labels: List[str] = data.get("names", [])
    return PlasticWasteDetector(weights=weights_path, labels=labels)
