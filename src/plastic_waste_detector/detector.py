"""Core inference helpers for the plastic waste detection project."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import time

import cv2
import torch
from PIL import Image
from torchvision.transforms import functional as F

from models.yolo import attempt_load
from utils.general import non_max_suppression


class PlasticWasteDetector:
    """Wraps a YOLOv5 model checkpoint to provide inference utilities."""

    def __init__(
        self,
        weights: Path | str,
        labels: Sequence[str],
        size: int = 640,
        confidence: float = 0.5,
        threshold: float = 0.3,
    ) -> None:
        self.confidence = float(confidence)
        self.threshold = float(threshold)
        self.size = int(size)
        self.labels = list(labels)

        checkpoint = Path(weights)
        if not checkpoint.exists():
            raise FileNotFoundError(f"Model weights not found: {checkpoint}")

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        try:
            self.model = attempt_load(str(checkpoint))
        except Exception as exc:  # pragma: no cover - depends on torch internals
            raise ValueError("Failed to load model file (.pt)") from exc

        self.model.eval()

    def __call__(self, image) -> Tuple[List[Dict[str, float | int | List[float]]], float]:
        return self.inference(image)

    def inference(self, image) -> Tuple[List[Dict[str, float | int | List[float]]], float]:
        """Run the network on a BGR image and return detections with latency."""

        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_image).resize((self.size, self.size), Image.BICUBIC)
        tensor = F.to_tensor(pil_img).unsqueeze(0).to(self.device)

        start = time.perf_counter()
        with torch.no_grad():
            pred = self.model(tensor)[0]
        inference_time = time.perf_counter() - start

        pred = non_max_suppression(pred, self.confidence, self.threshold)[0]

        detections: List[Dict[str, float | int | List[float]]] = []
        if pred is None or len(pred) == 0:
            return detections, float(inference_time)

        pred[:, :4] = scale_coords(tensor.shape[2:], pred[:, :4], image.shape).round()

        for *box, conf, class_id in pred:
            x1, y1, x2, y2 = box
            detection: Dict[str, float | int | List[float]] = {
                "box": [float(x1), float(y1), float(x2 - x1), float(y2 - y1)],
                "confidence": float(conf),
                "class_id": int(class_id),
            }
            detections.append(detection)

        return detections, float(inference_time)


def scale_coords(img_shape, coords, img0_shape):
    gain = min(img_shape[0] / img0_shape[0], img_shape[1] / img0_shape[1])
    pad_x = (img_shape[1] - img0_shape[1] * gain) / 2
    pad_y = (img_shape[0] - img0_shape[0] * gain) / 2
    coords[:, [0, 2]] -= pad_x
    coords[:, [1, 3]] -= pad_y
    coords[:, :4] /= gain
    clip_coords(coords, img0_shape)
    return coords.round()


def clip_coords(coords, img_shape):
    coords[:, 0].clamp_(0, img_shape[1])  # x1
    coords[:, 1].clamp_(0, img_shape[0])  # y1
    coords[:, 2].clamp_(0, img_shape[1])  # x2
    coords[:, 3].clamp_(0, img_shape[0])  # y2
    return coords
