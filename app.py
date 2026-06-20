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
import numpy as np
import torch
from flask import Flask, Response, jsonify, render_template

_controller = None  # hardware motor/relay controller (optional)

try:
    from plastic_waste_detector.pi_controller import WasteSorterController
    _HAS_HW = True
except Exception:
    _HAS_HW = False

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
for _p in (str(ROOT), str(SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

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
        self._raw_frame = None
        self._raw_lock = threading.Lock()
        self._last_det = np.zeros((0, 6))
        self._det_lock = threading.Lock()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._infer_thread = threading.Thread(target=self._inference_loop, daemon=True)

    def start(self) -> None:
        print(f"[INFO] Loading model: {self.weights}")
        from models.experimental import attempt_load
        from utils.general import non_max_suppression

        self.model = attempt_load(str(self.weights))
        self.model.eval()
        self._nms = non_max_suppression

        names = getattr(self.model, "names", None)
        if isinstance(names, list):
            self.names = {i: n for i, n in enumerate(names)}
        elif isinstance(names, dict):
            self.names = names
        else:
            classes_txt = ROOT / "classes.txt"
            if classes_txt.exists():
                self.names = {
                    i: ln.strip()
                    for i, ln in enumerate(classes_txt.read_text().splitlines())
                    if ln.strip()
                }
        print(f"[INFO] Model loaded. Classes: {self.names}")
        self._thread.start()
        self._infer_thread.start()

    def stop(self) -> None:
        self._stopped.set()

    def _capture_loop(self) -> None:
        """Reads camera at full speed (~30 FPS), overlays last known detections."""
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

            # Share raw frame with inference thread
            with self._raw_lock:
                self._raw_frame = frame.copy()

            # Draw last known detections (from inference thread)
            with self._det_lock:
                det = self._last_det.copy()

            counts: Dict[str, int] = defaultdict(int)
            detections = []
            last_label, last_conf = "—", 0.0

            for x1, y1, x2, y2, conf, cls_id in det:
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                cls = int(cls_id)
                name = self.names.get(cls, str(cls))
                color = _COLORS[cls % len(_COLORS)]
                label_text = f"{name}  {conf:.2f}"

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
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

            # FPS overlay
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

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                with _frame_lock:
                    _latest_frame = buf.tobytes()

            with _state_lock:
                _state["fps"] = round(fps, 1)
                _state["detections"] = detections
                _state["counts"] = dict(counts)
                _state["last_label"] = last_label
                _state["last_conf"] = round(last_conf, 3)
                _state["frame_count"] += 1
                _state["camera_ok"] = True

            if _controller is not None:
                for name in counts:
                    _controller.push_detection(name)

        cap.release()

    def _inference_loop(self) -> None:
        """Runs model inference on latest frames (~1 FPS on Pi), updates cached detections."""
        while not self._stopped.is_set():
            with self._raw_lock:
                frame = self._raw_frame
                if frame is not None:
                    frame = frame.copy()

            if frame is None:
                time.sleep(0.01)
                continue

            h0, w0 = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            r = self.size / max(h0, w0)
            h1, w1 = int(h0 * r), int(w0 * r)
            img = cv2.resize(rgb, (w1, h1))
            dh, dw = self.size - h1, self.size - w1
            img = cv2.copyMakeBorder(
                img, 0, dh, 0, dw, cv2.BORDER_CONSTANT, value=(114, 114, 114)
            )
            img_t = (
                torch.from_numpy(np.ascontiguousarray(img.transpose(2, 0, 1)))
                .float()
                .div(255.0)
                .unsqueeze(0)
            )

            t0 = time.perf_counter()
            with torch.no_grad():
                pred = self.model(img_t)[0]
            inf_ms = (time.perf_counter() - t0) * 1000

            preds = self._nms(pred, self.conf, self.iou)[0]
            if preds is not None and len(preds):
                p = preds.cpu().numpy()
                p[:, [0, 2]] = np.clip(p[:, [0, 2]] / self.size * w0, 0, w0)
                p[:, [1, 3]] = np.clip(p[:, [1, 3]] / self.size * h0, 0, h0)
                det = p
            else:
                det = np.zeros((0, 6))

            with self._det_lock:
                self._last_det = det

            with _state_lock:
                _state["inference_ms"] = round(inf_ms, 1)


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

    if _HAS_HW:
        global _controller
        try:
            _controller = WasteSorterController(
                detection_threshold=3,
                collection_time=3.0,
                movement_timeout=15.0,
            )
            hw_thread = threading.Thread(target=_controller.run, daemon=True)
            hw_thread.start()
            print("[INFO] Hardware controller started (detects via web app)")
        except Exception as exc:
            print(f"[WARN] Hardware controller failed to start: {exc}")
            _controller = None
    else:
        print("[INFO] Hardware controller unavailable (run on Raspberry Pi)")

    print(f"\n[INFO] Web UI available at  http://{args.host}")
    print(f"[INFO] On Raspberry Pi use  http://<pi-ip>  (no port needed)\n")

    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
