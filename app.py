"""Real-time Plastic Waste Detection Web UI.

Streams live camera feed with YOLOv5 detections overlaid.
Accessible from any browser on the same network – ideal for Raspberry Pi.

Usage:
    python app.py                      # webcam 0, port 5000
    python app.py --source 1           # different camera index
    python app.py --size 320           # recommended for Pi (faster inference)
    python app.py --host 0.0.0.0       # bind all interfaces (default)
    python app.py --port 8080          # custom port
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import torch
from flask import Flask, Response, jsonify, render_template

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# BGR colours per class (matches run_desktop.py palette converted for cv2)
_COLORS = [
    (83, 200, 0),    # green  – cable
    (243, 150, 33),  # blue   – plastic bottle
    (54, 67, 244),   # red    – soap bottle
    (7, 193, 255),   # amber  – sterofoam
    (176, 39, 156),  # purple – plastic bag
    (212, 188, 0),   # cyan   – plastic cup
]

# ── Shared state (updated by camera thread, read by Flask threads) ──────────

_state_lock = threading.Lock()
_state: Dict[str, Any] = {
    "fps": 0.0,
    "inference_ms": 0.0,
    "detections": [],
    "counts": {},
    "last_label": "—",
    "last_conf": 0.0,
    "frame_count": 0,
    "camera_ok": False,
}

_frame_lock = threading.Lock()
_latest_frame: Optional[bytes] = None

# ── Camera + detection thread ────────────────────────────────────────────────

class DetectionCamera:
    """Runs capture and inference in a background daemon thread."""

    def __init__(
        self,
        source: str,
        weights: str,
        size: int,
        conf: float,
        iou: float,
    ) -> None:
        self.source = source
        self.size = size
        self.conf = conf
        self.iou = iou
        self.weights = weights
        self.names: Dict[int, str] = {}
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)

    def start(self) -> None:
        print(f"[INFO] Loading model: {self.weights}")
        self.model = torch.hub.load(
            "ultralytics/yolov5",
            "custom",
            path=self.weights,
            force_reload=False,
            verbose=False,
        )
        self.model.conf = self.conf
        self.model.iou = self.iou
        self.names = self.model.names  # {0: 'cable', 1: 'plastic bottle', …}
        print(f"[INFO] Model loaded. Classes: {self.names}")
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()

    def _capture_loop(self) -> None:
        global _latest_frame, _state

        src: int | str = int(self.source) if self.source.isdigit() else self.source
        cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            print(f"[ERROR] Cannot open camera source: {self.source}")
            return

        fps_times: deque = deque(maxlen=30)

        while not self._stopped.is_set():
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            t0 = time.perf_counter()

            # ── Inference ────────────────────────────────────────────────────
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.model(rgb, size=self.size)
            inf_ms = (time.perf_counter() - t0) * 1000

            det = results.xyxy[0].cpu().numpy()  # [x1,y1,x2,y2,conf,cls]

            # ── Draw boxes & collect stats ───────────────────────────────────
            counts: Dict[str, int] = defaultdict(int)
            detections = []
            last_label, last_conf = "—", 0.0

            for x1, y1, x2, y2, conf, cls_id in det:
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                cls = int(cls_id)
                name = self.names.get(cls, str(cls))
                color = _COLORS[cls % len(_COLORS)]
                label_text = f"{name}  {conf:.2f}"

                # Bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                # Label background
                (tw, th), _ = cv2.getTextSize(
                    label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1
                )
                cv2.rectangle(
                    frame, (x1, y1 - th - 10), (x1 + tw + 6, y1), color, cv2.FILLED
                )
                cv2.putText(
                    frame,
                    label_text,
                    (x1 + 3, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

                counts[name] += 1
                detections.append(
                    {"label": name, "confidence": round(float(conf), 3), "class_id": cls}
                )
                if float(conf) > last_conf:
                    last_label, last_conf = name, float(conf)

            # ── FPS overlay ──────────────────────────────────────────────────
            fps_times.append(time.perf_counter())
            fps = (
                len(fps_times) / (fps_times[-1] - fps_times[0] + 1e-9)
                if len(fps_times) > 1
                else 0.0
            )
            cv2.putText(
                frame,
                f"FPS: {fps:.1f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

            # ── Encode & publish frame ────────────────────────────────────────
            ok, buf = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80]
            )
            if ok:
                with _frame_lock:
                    _latest_frame = buf.tobytes()

            with _state_lock:
                _state["fps"] = round(fps, 1)
                _state["inference_ms"] = round(inf_ms, 1)
                _state["detections"] = detections
                _state["counts"] = dict(counts)
                _state["last_label"] = last_label
                _state["last_conf"] = round(last_conf, 3)
                _state["frame_count"] += 1
                _state["camera_ok"] = True

        cap.release()


# ── Flask app ────────────────────────────────────────────────────────────────

app = Flask(__name__)
camera: Optional[DetectionCamera] = None


def _gen_frames():
    """MJPEG multipart generator consumed by /video_feed."""
    while True:
        with _frame_lock:
            frame = _latest_frame
        if frame is None:
            time.sleep(0.04)
            continue
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        )
        time.sleep(0.033)  # soft-cap browser stream at ~30 fps


@app.route("/")
def index():
    classes = list(camera.names.values()) if camera else []
    return render_template("index.html", classes=classes)


@app.route("/video_feed")
def video_feed():
    return Response(
        _gen_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/api/stats")
def api_stats():
    with _state_lock:
        return jsonify(dict(_state))


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    global camera

    parser = argparse.ArgumentParser(
        description="Plastic Waste Detector – Real-time Web UI"
    )
    parser.add_argument(
        "--source", default="0", help="Camera index or video/image path (default: 0)"
    )
    parser.add_argument(
        "--weights", default=str(ROOT / "best.pt"), help="Path to .pt weights file"
    )
    parser.add_argument(
        "--size",
        type=int,
        default=320,
        help="Inference image size (use 320 for Pi, 640 for desktop). Default: 320",
    )
    parser.add_argument("--conf", type=float, default=0.4, help="Confidence threshold")
    parser.add_argument("--iou", type=float, default=0.3, help="IOU threshold for NMS")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Flask bind address. 0.0.0.0 makes it reachable on the local network",
    )
    parser.add_argument("--port", type=int, default=80, help="Flask port (default: 80, no port needed in browser)")
    args = parser.parse_args()

    camera = DetectionCamera(
        source=args.source,
        weights=args.weights,
        size=args.size,
        conf=args.conf,
        iou=args.iou,
    )
    camera.start()

    print(f"\n[INFO] Web UI available at  http://{args.host}")
    print(f"[INFO] On Raspberry Pi use  http://<pi-ip>  (no port needed)\n")

    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
