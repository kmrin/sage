from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from PIL import Image, ImageSequence, UnidentifiedImageError

from core.http import MAX_UPLOAD, TooLargeError

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ("Animation", "BadImageError", "Encoded", "encode_gif", "fit_upload", "load")

MAX_FRAMES: Final = 120
MAX_STILL_SIDE: Final = 1600
MAX_ANIMATED_SIDE: Final = 512
MIN_DURATION: Final = 20  # ms, what actually plays
TRANSPARENT: Final = 255  # palette index reserved for transparency in GIFs
_ALPHA_CUTOFF: Final = 128
# Alpha -> mask lookup: pixels under the cutoff become the transparent index
_SEE_THROUGH: Final = [255] * _ALPHA_CUTOFF + [0] * (256 - _ALPHA_CUTOFF)


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


def load(data: bytes) -> Animation:
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
    animation: Animation, encode: Callable[[Animation], Encoded], *, attempts: int = 4
) -> Encoded:
    for _ in range(attempts):
        encoded = encode(animation)
        if len(encoded.data) <= MAX_UPLOAD:
            return encoded
        animation = animation.scaled(0.75)
    raise TooLargeError(f"Still over {MAX_UPLOAD} bytes after {attempts} tries")
