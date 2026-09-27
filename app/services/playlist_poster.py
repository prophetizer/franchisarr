"""A poster for a Franchisarr playlist, so it doesn't wear Plex's four-tile mosaic.

Square, because Plex shows playlists square: a tall poster was cropped to its middle and lost
its text (0.28.0). The top 9:16 of the square is the franchise or collection backdrop, whole --
a backdrop is already that shape, so none of it is cut -- fading into a dark panel that carries
the name, "In release order" and what's in it. Director pages have no backdrop, so the top is
two rows of the director's film posters instead.

Images come from TMDb's CDN, fetched by the server -- the one place Franchisarr downloads artwork
itself rather than leaving it to the browser -- so SHOW_ARTWORK=false means no poster. Anything
going wrong here returns None: a playlist without a custom poster is fine; a playlist that
failed because of its poster is not.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

SIZE = 1000
#: The artwork band across the top: the shape of a TMDb backdrop, so it isn't cropped.
ART_HEIGHT = SIZE * 9 // 16
FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
TIMEOUT = 20
#: Nord frost, the app's own accent, for the "In release order" line.
ACCENT = (136, 192, 208)
INK = (8, 10, 16)


def _fetch(url: str):  # noqa: ANN202 - a PIL image
    from PIL import Image

    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return Image.open(io.BytesIO(response.content)).convert("RGB")


def _fit(image, width: int, height: int):  # noqa: ANN001, ANN202
    from PIL import Image, ImageOps

    return ImageOps.fit(image, (width, height), Image.LANCZOS, centering=(0.5, 0.4))


def _darken_bottom(image, start: float, strength: int):  # noqa: ANN001, ANN202
    """Fade to near-black from `start` (a fraction of the height) down, so white text reads on
    any artwork."""
    from PIL import Image

    mask = Image.new("L", (1, image.height))
    for y in range(image.height):
        t = max(0.0, (y / image.height - start) / (1 - start))
        mask.putpixel((0, y), int(strength * t ** 1.2))
    return Image.composite(Image.new("RGB", image.size, INK), image, mask.resize(image.size))


def _poster_rows(urls: list[str]):  # noqa: ANN202
    """The director's film posters filling the artwork band, in a grid sized to how many there
    are so no cell is left empty: two rows of five (200x281, almost a poster's own 2:3) for ten
    or more, fewer columns for fewer films, one row below six."""
    from PIL import Image

    count = min(len(urls), 10)
    columns, rows = ((5, 2) if count >= 10 else (4, 2) if count >= 8 else (3, 2) if count >= 6
                     else (max(count, 1), 1))
    band = Image.new("RGB", (SIZE, ART_HEIGHT), INK)
    cell_w, cell_h = SIZE // columns, ART_HEIGHT // rows
    for i, url in enumerate(urls[:columns * rows]):
        try:
            band.paste(_fit(_fetch(url), cell_w, cell_h), ((i % columns) * cell_w, (i // columns) * cell_h))
        except Exception:  # noqa: BLE001 -- one missing tile leaves a dark cell, not no poster
            logger.debug("Poster tile %s unavailable", url)
    return band


def _font(bold: bool, size: int):  # noqa: ANN202
    from PIL import ImageFont

    return ImageFont.truetype(str(FONTS / ("NotoSans-Bold.ttf" if bold else "NotoSans-Regular.ttf")), size)


def _caption(films: int, episodes: int) -> str:
    parts = []
    if films:
        parts.append(f"{films} film{'' if films == 1 else 's'}")
    if episodes:
        parts.append(f"{episodes} episode{'' if episodes == 1 else 's'}")
    return " · ".join(parts)


def _name_lines(draw, name: str):  # noqa: ANN001, ANN202
    """The name as one line at the largest size that fits, or two balanced lines if one would
    have to shrink below readable at thumbnail size. Returns (lines, font)."""
    limit = SIZE - 110
    for size in range(104, 63, -4):
        if draw.textlength(name, font=_font(True, size)) <= limit:
            return [name], _font(True, size)
    words = name.split()
    if len(words) > 1:
        best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
        lines = [" ".join(words[:best]), " ".join(words[best:])]
        for size in range(72, 39, -4):
            if all(draw.textlength(line, font=_font(True, size)) <= limit for line in lines):
                return lines, _font(True, size)
        return lines, _font(True, 40)
    size = 64
    while size > 36 and draw.textlength(name, font=_font(True, size)) > limit:
        size -= 4
    return [name], _font(True, size)


def render(name: str, *, films: int, episodes: int, backdrop_url: str | None = None,
           poster_urls: list[str] | None = None) -> bytes | None:
    """The square poster as JPEG bytes, or None if there's no artwork to build it from (or it
    failed)."""
    from app.services.artwork import images_enabled

    if not images_enabled():
        return None
    try:
        from PIL import Image, ImageDraw

        if backdrop_url:
            band = _fit(_fetch(backdrop_url), SIZE, ART_HEIGHT)
        elif poster_urls:
            band = _poster_rows(poster_urls)
        else:
            return None

        image = Image.new("RGB", (SIZE, SIZE), INK)
        image.paste(_darken_bottom(band, start=0.70, strength=255), (0, 0))
        draw = ImageDraw.Draw(image)

        lines, font = _name_lines(draw, name)
        caption = _caption(films, episodes)
        # Laid out upward from the foot: mark, caption, "in release order", then the name.
        y = SIZE - 105 if caption else SIZE - 150
        if caption:
            draw.text((SIZE // 2, y), caption, font=_font(False, 36), fill=(210, 210, 210), anchor="ms")
        y -= 48
        draw.text((SIZE // 2, y), "IN RELEASE ORDER", font=_font(True, 32), fill=ACCENT, anchor="ms")
        line_height = int(font.size * 1.1)
        y -= 60
        for line in reversed(lines):
            draw.text((SIZE // 2, y), line, font=font, fill=(245, 245, 245), anchor="ms")
            y -= line_height
        draw.text((SIZE // 2, SIZE - 28), "FRANCHISARR", font=_font(True, 22), fill=(150, 150, 150), anchor="ms")

        out = io.BytesIO()
        image.save(out, format="JPEG", quality=88)
        return out.getvalue()
    except Exception:  # noqa: BLE001 -- the playlist matters; its poster is a nicety
        logger.warning("Couldn't make a poster for %r", name, exc_info=True)
        return None
