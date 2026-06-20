"""Patch heavy / hardware dependencies so the test suite runs on any host
(including non-Pi) without a GPU, camera, or I2C hardware."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

# ── sys.path: make project root and src/ importable ─────────────────────────
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
for p in (str(ROOT), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

# ── torch ────────────────────────────────────────────────────────────────────
_torch = MagicMock()
_torch.device.side_effect = lambda x: x
_torch.cuda.is_available.return_value = False
_ctx = MagicMock()
_ctx.__enter__ = MagicMock(return_value=None)
_ctx.__exit__ = MagicMock(return_value=False)
_torch.no_grad.return_value = _ctx
sys.modules["torch"] = _torch

# ── cv2 ──────────────────────────────────────────────────────────────────────
_cv2 = MagicMock()
_cv2.COLOR_BGR2RGB = 4
sys.modules["cv2"] = _cv2

# ── PIL ──────────────────────────────────────────────────────────────────────
_pil_image_mod = MagicMock()
sys.modules["PIL"] = MagicMock(Image=_pil_image_mod)
sys.modules["PIL.Image"] = _pil_image_mod

# ── torchvision ───────────────────────────────────────────────────────────────
_tvf = MagicMock()
sys.modules["torchvision"] = MagicMock()
sys.modules["torchvision.transforms"] = MagicMock()
sys.modules["torchvision.transforms.functional"] = _tvf

# ── internal project YOLO / utils (heavy deps, skip loading) ─────────────────
sys.modules["models"] = MagicMock()
sys.modules["models.yolo"] = MagicMock()
sys.modules["utils"] = MagicMock()
sys.modules["utils.general"] = MagicMock()

# ── Raspberry Pi hardware ─────────────────────────────────────────────────────
_rpi_gpio = MagicMock()
_rpi_gpio.RPI_REVISION = 2          # causes BUS_NUMBER = 1 in i2c_dev
_rpi_gpio.LOW = 0
_rpi_gpio.HIGH = 1
sys.modules["RPi"] = MagicMock(GPIO=_rpi_gpio)
sys.modules["RPi.GPIO"] = _rpi_gpio

_smbus_mod = MagicMock()
sys.modules["smbus"] = _smbus_mod
# NOTE: "drivers" is intentionally NOT mocked here so test_drivers.py can
# import the real drivers package (which will use the mocked smbus / RPi.GPIO).
