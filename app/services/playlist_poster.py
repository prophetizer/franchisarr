"""A poster for a Franchisarr playlist, so it doesn't wear Plex's four-tile mosaic.

The franchise or collection backdrop, cropped to a poster and darkened toward the bottom, with
the name, "In release order" and what's in it. Director pages have no backdrop, so they get a
mosaic of the director's first films instead, under the same text.

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

WIDTH, HEIGHT = 1000, 1500
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


def _mosaic(urls: list[str]):  # noqa: ANN202
    from PIL import Image

    canvas = Image.new("RGB", (WIDTH, HEIGHT), INK)
    cell_w, cell_h = WIDTH // 3, HEIGHT // 3
    for i, url in enumerate(urls[:9]):
        try:
            canvas.paste(_fit(_fetch(url), cell_w, cell_h), ((i % 3) * cell_w, (i // 3) * cell_h))
        except Exception:  # noqa: BLE001 -- one missing tile leaves a dark cell, not no poster
            logger.debug("Poster tile %s unavailable", url)
    return canvas


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


def render(name: str, *, films: int, episodes: int, backdrop_url: str | None = None,
           poster_urls: list[str] | None = None) -> bytes | None:
    """The poster as JPEG bytes, or None if there's no artwork to build it from (or it failed)."""
    from app.services.artwork import images_enabled

    if not images_enabled():
        return None
    try:
        from PIL import ImageDraw

        if backdrop_url:
            image = _darken_bottom(_fit(_fetch(backdrop_url), WIDTH, HEIGHT), start=0.45, strength=235)
        elif poster_urls:
            image = _darken_bottom(_mosaic(poster_urls), start=0.35, strength=245)
        else:
            return None

        draw = ImageDraw.Draw(image)
        size = 118
        while size > 48 and draw.textlength(name, font=_font(True, size)) > WIDTH - 120:
            size -= 4
        base = 1360
        draw.text((WIDTH // 2, base - 150), name, font=_font(True, size), fill=(245, 245, 245), anchor="ms")
        draw.text((WIDTH // 2, base - 80), "IN RELEASE ORDER", font=_font(True, 34), fill=ACCENT, anchor="ms")
        caption = _caption(films, episodes)
        if caption:
            draw.text((WIDTH // 2, base - 25), caption, font=_font(False, 40), fill=(210, 210, 210), anchor="ms")
        draw.text((WIDTH // 2, HEIGHT - 40), "FRANCHISARR", font=_font(True, 26), fill=(150, 150, 150), anchor="ms")

        out = io.BytesIO()
        image.save(out, format="JPEG", quality=88)
        return out.getvalue()
    except Exception:  # noqa: BLE001 -- the playlist matters; its poster is a nicety
        logger.warning("Couldn't make a poster for %r", name, exc_info=True)
        return None
