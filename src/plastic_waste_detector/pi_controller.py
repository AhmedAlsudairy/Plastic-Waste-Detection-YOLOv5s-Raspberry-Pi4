"""Runtime control loop for the Raspberry Pi deployment."""
from __future__ import annotations

from pathlib import Path
from typing import List

import threading
import time
import yaml

try:  # pragma: no cover - hardware dependency
    import RPi.GPIO as GPIO
except ModuleNotFoundError:  # pragma: no cover - allows development on non-Pi hosts
    GPIO = None  # type: ignore

from .detector import PlasticWasteDetector


class WasteSorterController:
    """GPIO motor/relay controller. Receives detections externally via push_detection()."""

    IR_PIN = 18
    RELAY_PIN = 14
    IN1 = 8
    IN2 = 7
    IN3 = 16
    IN4 = 20

    def __init__(
        self,
        detection_threshold: int = 3,
        collection_time: float = 3.0,
        movement_timeout: float = 15.0,
    ) -> None:
        if GPIO is None:
            raise RuntimeError(
                "GPIO is unavailable. Run on Raspberry Pi with RPi.GPIO installed"
            )

        self.detection_threshold = detection_threshold
        self.collection_time = collection_time
        self.movement_timeout = movement_timeout

        self.state: str = "IDLE"
        self._move_start: float = 0.0
        self._counts: dict[str, int] = {}
        self._running: bool = False
        self._lock = threading.Lock()

    def setup(self) -> None:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        GPIO.setup(self.IR_PIN, GPIO.IN)
        GPIO.setup(self.RELAY_PIN, GPIO.OUT, initial=GPIO.HIGH)

        for pin in (self.IN1, self.IN2, self.IN3, self.IN4):
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

        print(f"[MOTOR] GPIO ready  IR={self.IR_PIN} RLY={self.RELAY_PIN}  "
              f"IN1={self.IN1} IN2={self.IN2} IN3={self.IN3} IN4={self.IN4}")

    def run(self) -> None:
        """Main loop — handles state machine. No camera, no inference."""
        self.setup()
        self._running = True
        try:
            while self._running:
                if self.state == "MOVING":
                    self._move_forward()
                    self._process_moving_state()
                else:
                    time.sleep(0.05)
        finally:
            self._stop_motors()
            GPIO.cleanup()
            print("[MOTOR] Stopped")

    def stop(self) -> None:
        self._running = False

    def push_detection(self, label: str) -> None:
        """Called from web app capture thread every frame a waste object is seen."""
        with self._lock:
            if self.state != "IDLE":
                return

            cnt = self._counts.get(label, 0) + 1
            self._counts[label] = cnt

            if cnt >= self.detection_threshold:
                self._counts[label] = 0
                print(f"[MOTOR] Detected '{label}' ({cnt} frames)  ->  MOVING")
                self.state = "MOVING"
                self._move_start = time.perf_counter()

    # ── State machine helpers ──────────────────────────────────────────────

    def _process_moving_state(self) -> None:
        """Check IR sensor while moving; transition to COLLECTING on obstacle."""
        if time.perf_counter() - self._move_start > self.movement_timeout:
            self._stop_motors()
            print("[MOTOR] Movement timeout — back to IDLE")
            self.state = "IDLE"
            return

        if GPIO.input(self.IR_PIN) == GPIO.LOW:
            self._stop_motors()
            self._activate_relay()
            print(f"[MOTOR] IR triggered — relay ON ({self.collection_time}s)")
            self.state = "COLLECTING"
            time.sleep(self.collection_time)
            self._deactivate_relay()
            print("[MOTOR] Relay OFF — back to IDLE")
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
    """Load model and return a detector instance (used by scripts/run_pi.py)."""
    with open(data_yaml, "r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    labels: List[str] = data.get("names", [])
    return PlasticWasteDetector(weights=weights_path, labels=labels)
