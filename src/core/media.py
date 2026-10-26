from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

from core.http import MAX_UPLOAD, TooLargeError

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = (
    "Animation",
    "BadImageError",
    "Encoded",
    "encode_gif",
    "fit_upload",
    "has_transparency",
    "load",
    "prepare",
)

MAX_FRAMES: Final = 120
MAX_STILL_SIDE: Final = 1600
MAX_ANIMATED_SIDE: Final = 512
MIN_DURATION: Final = 20  # ms, what actually plays
TRANSPARENT: Final = 255  # palette index reserved for transparency in GIFs
_ALPHA_CUTOFF: Final = 128
# Alpha -> mask lookup: pixels under the cutoff become the transparent index
_SEE_THROUGH: Final = [255] * _ALPHA_CUTOFF + [0] * (256 - _ALPHA_CUTOFF)

SEND_STILL_SIDE: Final = 1280
SEND_ANIMATED_SIDE: Final = 480
SEND_STILL_BYTES: Final = 2 * 1024 * 1024
SEND_ANIMATED_BYTES: Final = 4 * 1024 * 1024
JPEG_QUALITY: Final = 85
_PASSTHROUGH: Final = {"JPEG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}


class BadImageError(ValueError):
    """The bytes aren't an image Pillow can read"""


@dataclass(slots=True)
class Animation:
    frames: list[Image.Image]
    durations: list[int] = field(default_factory=lambda: [0])
    loop: int = 0

    @property
    def animated(self) -> bool:
        return len(self.frames) > 1

    def map(self, edit: Callable[[Image.Image], Image.Image]) -> Animation:
        return Animation([edit(frame) for frame in self.frames], list(self.durations), self.loop)

    def scaled(self, factor: float) -> Animation:
        return self.map(lambda frame: _resize(frame, factor))


@dataclass(frozen=True, slots=True)
class Encoded:
    data: bytes
    extension: str


def load(data: bytes, *, max_side: int | None = None) -> Animation:
    try:
        source = Image.open(io.BytesIO(data))
        source.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise BadImageError(str(error)) from error

    with source:
        frames: list[Image.Image] = []
        durations: list[int] = []
        for frame in ImageSequence.Iterator(source):
            frames.append(frame.convert("RGBA"))
            durations.append(max(MIN_DURATION, int(frame.info.get("duration") or 100)))
        loop = int(source.info.get("loop", 0))

    animation = _thin_out(Animation(frames, durations, loop))
    if max_side is None:
        max_side = MAX_ANIMATED_SIDE if animation.animated else MAX_STILL_SIDE
    longest = max(animation.frames[0].size)
    return animation.scaled(max_side / longest) if longest > max_side else animation


def _thin_out(animation: Animation) -> Animation:
    """Keeps every n-th frame of long GIFs, adding up durations so the speed stays the same."""
    count = len(animation.frames)
    if count <= MAX_FRAMES:
        return animation
    step = math.ceil(count / MAX_FRAMES)
    frames = animation.frames[::step]
    durations = [sum(animation.durations[i : i + step]) for i in range(0, count, step)]
    return Animation(frames, durations, animation.loop)


def _resize(frame: Image.Image, factor: float) -> Image.Image:
    width, height = frame.size
    size = (max(1, round(width * factor)), max(1, round(height * factor)))
    return frame.resize(size, Image.Resampling.LANCZOS)


def encode_gif(animation: Animation) -> bytes:
    frames = [_to_palette(frame) for frame in animation.frames]
    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=animation.durations,
        loop=animation.loop,
        disposal=2,
        transparency=TRANSPARENT,
        optimize=False,
    )
    return buffer.getvalue()


def _to_palette(frame: Image.Image) -> Image.Image:
    rgba = frame.convert("RGBA")
    palette_image = rgba.convert("RGB").quantize(colors=255, dither=Image.Dither.NONE)
    palette = palette_image.getpalette() or []
    palette_image.putpalette(palette + [0] * (768 - len(palette)))
    see_through = rgba.getchannel("A").point(_SEE_THROUGH)
    palette_image.paste(TRANSPARENT, mask=see_through)
    palette_image.info["transparency"] = TRANSPARENT
    return palette_image


def fit_upload(
    animation: Animation,
    encode: Callable[[Animation], Encoded],
    *,
    attempts: int = 4,
    limit: int | None = None,
) -> Encoded:
    """Encodes, shrinking by a quarter each time the result is over `limit` (Discord's 10 MB)."""
    limit = MAX_UPLOAD if limit is None else limit
    for _ in range(attempts):
        encoded = encode(animation)
        if len(encoded.data) <= limit:
            return encoded
        animation = animation.scaled(0.75)
    raise TooLargeError(f"Still over {limit} bytes after {attempts} tries")


def has_transparency(frame: Image.Image) -> bool:
    # any pixel below full opacity leaves something behind once the alpha is inverted
    return ImageOps.invert(frame.convert("RGBA").getchannel("A")).getbbox() is not None


def prepare(data: bytes) -> Encoded:
    try:
        with Image.open(io.BytesIO(data)) as probe:
            kind, size = probe.format or "", probe.size
            animated = bool(getattr(probe, "is_animated", False))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise BadImageError(str(error)) from error

    side, byte_limit = (
        (SEND_ANIMATED_SIDE, SEND_ANIMATED_BYTES)
        if animated
        else (SEND_STILL_SIDE, SEND_STILL_BYTES)
    )
    extension = _PASSTHROUGH.get(kind)
    if extension and max(size) <= side and len(data) <= byte_limit:
        return Encoded(data, extension)

    animation = load(data, max_side=side)

    if animation.animated:
        return fit_upload(
            animation, lambda a: Encoded(encode_gif(a), "gif"), limit=SEND_ANIMATED_BYTES
        )

    frame = animation.frames[0]
    buffer = io.BytesIO()
    if has_transparency(frame):
        frame.save(buffer, format="PNG", optimize=True)
        return Encoded(buffer.getvalue(), "png")
    frame.convert("RGB").save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return Encoded(buffer.getvalue(), "jpg")
