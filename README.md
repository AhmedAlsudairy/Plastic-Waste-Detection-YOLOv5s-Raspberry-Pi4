# Plastic Waste Detection on Raspberry Pi 4B

This project contains the software for a Raspberry Pi powered sorter that detects
and classifies plastic waste using a custom YOLOv5s model. The system drives two
servos, an LCD, and uses an infrared sensor to automate the separation of
recyclable (PET, HDPE, PP) and non-recyclable plastics (PVC, PS, LDPE).

## Repository Layout
```
├── best.pt                    # Trained YOLOv5s weights
├── data.yaml                  # Class metadata generated from Roboflow export
├── dataset/
│   └── Dataset Link.txt       # Placeholder for the dataset download URL
├── scripts/
│   └── run_pi.py              # High-level launcher for the Raspberry Pi runtime
├── src/
│   └── plastic_waste_detector/
│       ├── detector.py        # YOLOv5 inference helper
│       ├── pi_controller.py   # GPIO/LCD control loop for the sorter
│       └── __init__.py
├── Deteksi.py                 # Legacy entry point (calls into src/)
├── Fungsi.py                  # Legacy compatibility wrapper for detector import
└── utils/, models/, drivers/  # Upstream YOLOv5 support modules
```

## Getting Started
1. **Install dependencies** on the Raspberry Pi:
   ```bash
   pip install -r requirements.txt
   ```
   The project follows Ultralytics' YOLOv5 requirements. If you are preparing a
   fresh image, install OpenCV (`sudo apt install python3-opencv`) and make sure
   the custom LCD driver in `drivers/` is available.

2. **Provide the dataset URL**: once the dataset is re-uploaded, paste the share
   link into `dataset/Dataset Link.txt`. This makes it easier to retrain or
   replicate the project.

3. **Run the sorter** (requires Raspberry Pi hardware, webcam, servos, LCD, and
   infrared sensor connected as in the final build):
   ```bash
   PYTHONPATH=src python scripts/run_pi.py
   ```
   The legacy command `python Deteksi.py` continues to work and simply forwards
   to the reorganized package.

## Training Notes
- A 6,000 image dataset was annotated on Roboflow covering plastic bottles,
  plastic bags, cups, cables, soap bottles, and styrofoam.
- The model was trained with YOLOv5s using a 70/20/10 train/val/test split.
- Performance on Raspberry Pi 4B (Ubuntu) reached ~2 FPS with accuracy 97.2%,
  precision 0.9995, recall 0.9993, and F1 score 0.9994.

## Hardware Control Overview
- Two servos are driven from GPIO pins 33 and 12, with duty cycles calibrated in
  `pi_controller.py` to route items into the correct chute.
- The LCD is updated to show the recycling stream and inference latency for each
  accepted detection.
- Detection counts debounce false positives; a class must be confirmed more than
  five times before actuating the servos.

## Contributing
- Keep Python sources under `src/`.
- Hardware-specific scripts or utilities can live under `scripts/`.
- Use `dataset/` for documentation and links related to data acquisition.

## References
- https://github.com/ultralytics/yolov5
- https://github.com/weirros/yolov5_wi_pi4
- https://jordan-johnston271.medium.com/tutorial-running-yolov5-machine-learning-detection-on-a-raspberry-pi-4-3938add0f719
- https://pub.towardsai.net/yolov5-m-implementation-from-scratch-with-pytorch-c8f84a66c98b
