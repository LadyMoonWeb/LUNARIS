"""Background picture of the Sky panorama.

The panorama chart draws a picture behind the Sun and Earth tracks. The
picture is a plain image file, so it can be replaced without touching code:

    assets/panorama_background.png   <- put your own drawing here (png / jpg / webp)
    assets/panorama_placeholder.png  <- flat-horizon placeholder, used until then

Mapping of the picture (it is stretched to fit, any pixel size works):
    left edge  = azimuth 0 deg (north), right edge = azimuth 360 deg
    top edge   = altitude +10 deg,      bottom edge = altitude -5 deg
so a flat horizon (altitude 0) lies two thirds of the way down.

Run ``python -m ui.panorama`` from the project root to regenerate the placeholder.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import numpy as np
from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "assets"
PLACEHOLDER = ASSETS / "panorama_placeholder.png"
CUSTOM_STEM = "panorama_background"
CUSTOM_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

AZ_MIN, AZ_MAX = 0.0, 360.0
ALT_MIN, ALT_MAX = -5.0, 10.0

MAX_WIDTH = 2400  # larger pictures are downscaled before being sent to the browser


def make_placeholder(width: int = 1800, height: int = 450) -> Image.Image:
    """Black sky over a smooth grey plain, horizon at altitude 0."""
    horizon_row = int(round(height * ALT_MAX / (ALT_MAX - ALT_MIN)))
    pixels = np.zeros((height, width, 3), dtype=np.uint8)

    # Sky: black, with a few faint stars.
    pixels[:horizon_row] = (4, 5, 8)
    rng = np.random.default_rng(7)
    for _ in range(140):
        x, y = rng.integers(0, width), rng.integers(0, max(horizon_row - 6, 1))
        pixels[y, x] = (int(rng.integers(70, 150)),) * 3

    # Ground: bright at the horizon, darker toward the observer.
    depth = np.linspace(0.0, 1.0, height - horizon_row)[:, None]
    grey = (118 - 62 * depth).astype(np.uint8)
    pixels[horizon_row:] = np.repeat(grey[:, :, None], 3, axis=2) * np.ones((1, width, 1), dtype=np.uint8)
    return Image.fromarray(pixels)


def custom_background_path() -> Path | None:
    for suffix in CUSTOM_SUFFIXES:
        path = ASSETS / f"{CUSTOM_STEM}{suffix}"
        if path.exists():
            return path
    return None


def background_path() -> tuple[Path | None, bool]:
    """Path of the picture to show and whether it is the owner's own picture."""
    custom = custom_background_path()
    if custom is not None:
        return custom, True
    return (PLACEHOLDER if PLACEHOLDER.exists() else None), False


def as_data_uri(path: Path | None) -> str:
    """The picture as a JPEG data URI (generated placeholder if no file exists)."""
    image = make_placeholder() if path is None else Image.open(path)
    image = image.convert("RGB")
    if image.width > MAX_WIDTH:
        image = image.resize((MAX_WIDTH, max(1, round(image.height * MAX_WIDTH / image.width))))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


if __name__ == "__main__":
    ASSETS.mkdir(exist_ok=True)
    make_placeholder().save(PLACEHOLDER)
    print(f"Placeholder written to {PLACEHOLDER}")
