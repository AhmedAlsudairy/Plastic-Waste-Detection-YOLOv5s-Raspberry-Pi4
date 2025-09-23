"""Runtime control loop for the Raspberry Pi deployment."""
from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class ServoConfig:
    pwm_pin: int
    neutral_duty_cycle: float
    active_duty_cycle: float


@dataclass
class SortingAction:
    label: str
    display_line: str
    servo1: ServoConfig
    servo2: ServoConfig


class WasteSorterController:
    """Encapsulates GPIO, LCD and detection loop for the sorter."""

    def __init__(
        self,
        detector: PlasticWasteDetector,
        classes: Iterable[str],
        capture_index: int = 0,
        detection_threshold: int = 5,
    ) -> None:
        if GPIO is None or drivers is None:
            raise RuntimeError(
                "GPIO or LCD drivers are unavailable. Run on Raspberry Pi with required libraries installed"
            )

        self.detector = detector
        self.classes = list(classes)
        self.capture_index = capture_index
        self.detection_threshold = detection_threshold

        self.display = drivers.Lcd()
        self.servo1_pwm = None
        self.servo2_pwm = None

        # Maps class names to sorting actions; duty cycles tuned from original script
        self.actions: Dict[str, SortingAction] = {
            "plastic bottle": SortingAction(
                label="PET",
                display_line="-Recycle-",
                servo1=ServoConfig(pwm_pin=33, neutral_duty_cycle=7.5, active_duty_cycle=11.5),
                servo2=ServoConfig(pwm_pin=12, neutral_duty_cycle=4.5, active_duty_cycle=9.0),
            ),
            "plastic cup": SortingAction(
                label="PP",
                display_line="-Recycle-",
                servo1=ServoConfig(pwm_pin=33, neutral_duty_cycle=7.5, active_duty_cycle=3.5),
                servo2=ServoConfig(pwm_pin=12, neutral_duty_cycle=4.5, active_duty_cycle=9.0),
            ),
            "soap bottle": SortingAction(
                label="HDPE",
                display_line="-Recycle-",
                servo1=ServoConfig(pwm_pin=33, neutral_duty_cycle=7.5, active_duty_cycle=3.5),
                servo2=ServoConfig(pwm_pin=12, neutral_duty_cycle=4.5, active_duty_cycle=1.2),
            ),
            "cable": SortingAction(
                label="PVC",
                display_line="-Non Recycle-",
                servo1=ServoConfig(pwm_pin=33, neutral_duty_cycle=7.5, active_duty_cycle=11.5),
                servo2=ServoConfig(pwm_pin=12, neutral_duty_cycle=4.5, active_duty_cycle=1.2),
            ),
            "sterofoam": SortingAction(
                label="PS",
                display_line="-Non Recycle-",
                servo1=ServoConfig(pwm_pin=33, neutral_duty_cycle=7.5, active_duty_cycle=11.5),
                servo2=ServoConfig(pwm_pin=12, neutral_duty_cycle=4.5, active_duty_cycle=1.2),
            ),
            "plastic bag": SortingAction(
                label="LDPE",
                display_line="-Non Recycle-",
                servo1=ServoConfig(pwm_pin=33, neutral_duty_cycle=7.5, active_duty_cycle=11.5),
                servo2=ServoConfig(pwm_pin=12, neutral_duty_cycle=4.5, active_duty_cycle=1.2),
            ),
        }

    def setup(self) -> None:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)

        self.display.lcd_clear()
        self.display.lcd_display_string("STAND", 1)
        self.display.lcd_display_string("BY", 2)

        infrared_pin = 38
        GPIO.setup(infrared_pin, GPIO.IN)

        servo1_pin = 33
        servo2_pin = 12
        GPIO.setup(servo1_pin, GPIO.OUT)
        GPIO.setup(servo2_pin, GPIO.OUT)

        self.servo1_pwm = GPIO.PWM(servo1_pin, 50)
        self.servo2_pwm = GPIO.PWM(servo2_pin, 50)

        neutral_servo1 = self.actions["plastic bottle"].servo1.neutral_duty_cycle
        neutral_servo2 = self.actions["plastic bottle"].servo2.neutral_duty_cycle

        self.servo1_pwm.start(neutral_servo1)
        time.sleep(1)
        self.servo1_pwm.ChangeDutyCycle(0)
        self.servo2_pwm.start(neutral_servo2)
        time.sleep(1)
        self.servo2_pwm.ChangeDutyCycle(0)

        self.display.lcd_clear()
        self.display.lcd_display_string("MENYALAKAN", 1)
        self.display.lcd_display_string("KAMERA", 2)
        time.sleep(2)
        self.display.lcd_clear()

    def run(self) -> None:
        self.setup()
        capture = cv2.VideoCapture(self.capture_index)
        counts = {name: 0 for name in self.actions}

        try:
            while True:
                ret, frame = capture.read()
                if not ret:
                    continue

                frame = cv2.flip(frame, 1)
                detections, latency = self.detector.inference(frame)

                for detection in detections:
                    self._handle_detection(detection, counts, latency)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        finally:
            capture.release()
            cv2.destroyAllWindows()
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

        action = self.actions.get(label)
        if not action:
            return

        self.display.lcd_display_string(action.display_line, 1)
        time.sleep(1)
        self.display.lcd_display_string(action.label, 2)

        self._swing_servo(self.servo1_pwm, action.servo1)
        self._swing_servo(self.servo2_pwm, action.servo2)

        self.display.lcd_clear()
        self.display.lcd_display_string("Waktu Komputasi:", 1)
        self.display.lcd_display_string(f"{latency:.3f}s", 2)
        time.sleep(4)
        self.display.lcd_clear()

        counts[label] = 0

    @staticmethod
    def _swing_servo(pwm, config: ServoConfig) -> None:
        if pwm is None:
            return

        pwm.ChangeDutyCycle(config.active_duty_cycle)
        time.sleep(4)
        pwm.ChangeDutyCycle(config.neutral_duty_cycle)
        time.sleep(4)
        pwm.ChangeDutyCycle(0)


def build_detector(weights_path: Path | str, data_yaml: Path | str) -> PlasticWasteDetector:
    with open(data_yaml, "r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    labels: List[str] = data.get("names", [])
    return PlasticWasteDetector(weights=weights_path, labels=labels)
