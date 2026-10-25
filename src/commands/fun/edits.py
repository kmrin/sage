from __future__ import annotations

import io
import math
from typing import Final

from PIL import Image, ImageChops, ImageEnhance, ImageOps

from core.media import Animation, Encoded, encode_gif

__all__ = ("deepfry", "jpegify", "pixelate")

FRY_TINT: Final = (255, 100, 0)
PIXELS_ACROSS: Final = 40  # pixelate to roughly this many blocks on the longest side
_JPEG_BACKGROUND: Final = (255, 255, 255)
_MIN_CRUNCH_SIDE: Final = 200


def deepfry(animation: Animation) -> Encoded:
    fried = animation.map(_fry)
    if fried.animated:
        return Encoded(encode_gif(fried), "gif")
    frame = fried.frames[0]
    if _has_transparency(frame):
        return Encoded(_png(frame), "png")
    return Encoded(_jpeg(frame.convert("RGB"), quality=25), "jpg")


def _fry(frame: Image.Image) -> Image.Image:
    alpha = frame.getchannel("A")
    image = frame.convert("RGB")
    image = ImageEnhance.Color(image).enhance(3.0)
    image = ImageEnhance.Contrast(image).enhance(1.8)
    image = ImageEnhance.Brightness(image).enhance(1.1)
    image = ImageEnhance.Sharpness(image).enhance(8.0)
    image = Image.blend(image, Image.new("RGB", image.size, FRY_TINT), 0.15)
    # effect_noise is centered on 128, so the offset keeps the brightness where it was
    noise = Image.effect_noise(image.size, 30).convert("RGB")
    image = ImageChops.add(image, noise, scale=1.0, offset=-128)
    image = _crunch(image, quality=12, scale=0.6)
    image.putalpha(alpha)
    return image


def jpegify(animation: Animation) -> Encoded:
    frame = animation.frames[0]
    flat = Image.new("RGB", frame.size, _JPEG_BACKGROUND)
    flat.paste(frame, mask=frame.getchannel("A"))
    return Encoded(_jpeg(_crunch(flat, quality=6, scale=0.5), quality=4), "jpg")


def pixelate(animation: Animation) -> Encoded:
    pixelated = animation.map(_pixelate)
    if pixelated.animated:
        return Encoded(encode_gif(pixelated), "gif")
    return Encoded(_png(pixelated.frames[0]), "png")


def _pixelate(frame: Image.Image) -> Image.Image:
    width, height = frame.size
    block = max(2, round(max(width, height) / PIXELS_ACROSS))
    small = frame.resize(
        (math.ceil(width / block), math.ceil(height / block)), Image.Resampling.BOX
    )
    return small.resize((width, height), Image.Resampling.NEAREST)


def _crunch(image: Image.Image, *, quality: int, scale: float) -> Image.Image:
    width, height = image.size
    scale = min(1.0, max(scale, _MIN_CRUNCH_SIDE / min(width, height)))
    small = image.resize((max(1, round(width * scale)), max(1, round(height * scale))))
    with Image.open(io.BytesIO(_jpeg(small, quality=quality))) as crunched:
        return crunched.convert("RGB").resize((width, height), Image.Resampling.NEAREST)


def _has_transparency(frame: Image.Image) -> bool:
    # any pixel below full opacity leaves something behind once the alpha is inverted
    return ImageOps.invert(frame.getchannel("A")).getbbox() is not None


def _jpeg(image: Image.Image, *, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
