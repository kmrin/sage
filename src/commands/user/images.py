from __future__ import annotations

import functools
import io
from typing import Final

from PIL import Image

from core.media import Animation, encode_gif
from core.paths import paths

__all__ = ("PET_FRAMES", "PET_SIZE", "render_petpet")

PET_FRAMES: Final = 10
PET_SIZE: Final = (128, 128)
PET_FRAME_MS: Final = 20


@functools.cache
def _hand(index: int) -> Image.Image:
    with Image.open(paths.asset("images", "petpet", f"pet{index}.gif")) as hand:
        return hand.convert("RGBA").resize(PET_SIZE, Image.Resampling.LANCZOS)


def render_petpet(avatar: bytes) -> bytes:
    width, height = PET_SIZE
    with Image.open(io.BytesIO(avatar)) as source:
        base = source.convert("RGBA").resize(PET_SIZE, Image.Resampling.LANCZOS)

    frames: list[Image.Image] = []
    for index in range(PET_FRAMES):
        # squeezes in for the first half, back out for the second
        squeeze = index if index < PET_FRAMES / 2 else PET_FRAMES - index
        scale_x = 0.8 + squeeze * 0.02
        scale_y = 0.8 - squeeze * 0.05
        offset_x = (1 - scale_x) * 0.5 + 0.1
        offset_y = (1 - scale_y) - 0.08

        canvas = Image.new("RGBA", PET_SIZE, (0, 0, 0, 0))
        squished = base.resize((round(scale_x * width), round(scale_y * height)))
        canvas.paste(squished, (round(offset_x * width), round(offset_y * height)))
        hand = _hand(index)
        canvas.paste(hand, mask=hand)
        frames.append(canvas)

    return encode_gif(Animation(frames, [PET_FRAME_MS] * PET_FRAMES, loop=0))
