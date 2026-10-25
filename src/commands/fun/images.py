from __future__ import annotations

import functools
import io
from dataclasses import dataclass
from typing import Final

from PIL import Image, ImageDraw, ImageFont, ImageOps

from core.paths import paths

__all__ = ("QUOTE_SIZE", "fit_text", "render_quote", "render_sonic", "wrap")

FONT_FILE: Final = ("fonts", "MPLUSRounded1c-Bold.ttf")
SONIC_FILE: Final = ("images", "sonic.png")

# The empty blue area left of Sonic in the template
SONIC_BOX: Final = (45, 125, 715, 555)
QUOTE_SIZE: Final = (1200, 675)
QUOTE_TEXT_BOX: Final = (620, 70, 1160, 605)
ELLIPSIS: Final = "…"


@functools.cache
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(paths.asset(*FONT_FILE), size)


@dataclass(frozen=True, slots=True)
class FittedText:
    font: ImageFont.FreeTypeFont
    lines: list[str]
    line_height: int

    @property
    def height(self) -> int:
        return self.line_height * len(self.lines)


def wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """Word wrap that also breaks words (or spaceless text, like Japanese) wider than `width`."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}" if line else word
            if font.getlength(candidate) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
            rest = word
            while font.getlength(rest) > width:
                cut = _longest_fit(rest, font, width)
                lines.append(rest[:cut])
                rest = rest[cut:]
            line = rest
        lines.append(line)
    return lines


def _longest_fit(word: str, font: ImageFont.FreeTypeFont, width: int) -> int:
    low, high = 1, len(word)
    while low < high:
        middle = (low + high + 1) // 2
        if font.getlength(word[:middle]) <= width:
            low = middle
        else:
            high = middle - 1
    return low


def fit_text(
    text: str, width: int, height: int, *, max_size: int, min_size: int, spacing: float = 1.2
) -> FittedText:
    """The largest font size whose wrapped text fits the box, cut short with … at `min_size`."""
    for size in range(max_size, min_size - 1, -2):
        font = _font(size)
        line_height = round(size * spacing)
        lines = wrap(text, font, width)
        if line_height * len(lines) <= height:
            return FittedText(font, lines, line_height)

    font = _font(min_size)
    line_height = round(min_size * spacing)
    lines = wrap(text, font, width)[: max(1, height // line_height)]
    last = lines[-1]
    while last and font.getlength(last + ELLIPSIS) > width:
        last = last[:-1]
    lines[-1] = last.rstrip() + ELLIPSIS
    return FittedText(font, lines, line_height)


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    fitted: FittedText,
    center_x: float,
    top: float,
    fill: int | tuple[int, int, int],
    *,
    stroke: int = 0,
    stroke_fill: int | tuple[int, int, int] | None = None,
) -> None:
    for index, line in enumerate(fitted.lines):
        y = top + index * fitted.line_height + fitted.line_height / 2
        draw.text(
            (center_x, y),
            line,
            font=fitted.font,
            fill=fill,
            anchor="mm",
            stroke_width=stroke,
            stroke_fill=stroke_fill,
        )


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def render_sonic(text: str) -> bytes:
    with Image.open(paths.asset(*SONIC_FILE)) as template:
        image = template.convert("RGB")

    left, top, right, bottom = SONIC_BOX
    fitted = fit_text(text, right - left, bottom - top, max_size=72, min_size=22)
    stroke = max(2, round(fitted.font.size / 12))
    _draw_lines(
        ImageDraw.Draw(image),
        fitted,
        (left + right) / 2,
        top + (bottom - top - fitted.height) / 2,
        fill=(255, 255, 255),
        stroke=stroke,
        stroke_fill=(10, 20, 60),
    )
    return _png(image)


def render_quote(avatar: bytes | None, quote: str, name: str, handle: str) -> bytes:
    height = QUOTE_SIZE[1]
    image = Image.new("L", QUOTE_SIZE, 0)

    if avatar is not None:
        with Image.open(io.BytesIO(avatar)) as source:
            # transparent avatars go on black first, or their clear parts come out as noise
            flat = Image.new("RGBA", source.size, (0, 0, 0, 255))
            flat.alpha_composite(source.convert("RGBA"))
            portrait = ImageOps.fit(flat.convert("L"), (height, height))
        image.paste(portrait, (0, 0), _fade_mask(height, height))

    left, top, right, bottom = QUOTE_TEXT_BOX
    center_x = (left + right) / 2
    name_font, handle_font = _font(34), _font(26)
    name_gap, handle_gap = 34, 12
    footer = name_gap + round(name_font.size) + handle_gap + round(handle_font.size)

    text = f"“{quote.strip()}”"
    fitted = fit_text(
        text, right - left, bottom - top - footer, max_size=60, min_size=24, spacing=1.3
    )
    y = top + (bottom - top - fitted.height - footer) / 2

    draw = ImageDraw.Draw(image)
    _draw_lines(draw, fitted, center_x, y, fill=255)
    y += fitted.height + name_gap
    draw.text((center_x, y), f"- {name}", font=name_font, fill=255, anchor="ma")
    y += name_font.size + handle_gap
    draw.text((center_x, y), f"@{handle}", font=handle_font, fill=150, anchor="ma")

    return _png(image)


def _fade_mask(width: int, height: int) -> Image.Image:
    """Opaque for the left third, then fading out to fully transparent at the right edge."""
    solid = width // 3
    fade = width - solid
    row = [255 if x < solid else round(255 * (1 - (x - solid) / fade)) for x in range(width)]
    strip = Image.new("L", (width, 1))
    strip.putdata(row)
    return strip.resize((width, height))
