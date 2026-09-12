"""Generate the PWA icon set from the blueprint brand mark.

The repository has no logo file: the brand mark is a CSS text glyph
(``.brand-mark``), which cannot become a home-screen icon. This renders the
same treatment -- Barlow Condensed 700 on the primary ground, with blueprint
corner marks -- into the raster sizes Android and iOS require, and writes
`app/static/brand/icon.svg` as the editable source of record.

Deliberately stdlib + Pillow only. Pillow already ships with reportlab, which
is in requirements.txt, and the Barlow Condensed WOFF comes from the
@fontsource package already in package.json -- so this adds no dependency.
WOFF1 is zlib-compressed (unlike WOFF2's Brotli), so it decodes here without
fontTools.

Run: .venv/bin/python scripts/build_pwa_icons.py
Outputs are committed, exactly as scripts/build-icon-assets.mjs commits its SVGs.
"""

from __future__ import annotations

import io
import struct
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BRAND_DIR = ROOT / "app" / "static" / "brand"
WOFF = ROOT / "node_modules" / "@fontsource" / "barlow-condensed" / "files" / "barlow-condensed-latin-700-normal.woff"

# design-system/icc-erp/MASTER.md -- --color-primary and --color-canvas.
INK = "#f2f2f3"
GROUND = "#5980a6"
WORDMARK = "ICC"


def woff_to_sfnt(data: bytes) -> bytes:
    """Decode a WOFF1 container back into the plain SFNT (TTF/OTF) it wraps."""
    if data[:4] != b"wOFF":
        raise ValueError("not a WOFF file")
    flavor, _length, num_tables = struct.unpack(">4sIH", data[4:14])
    entries = []
    for i in range(num_tables):
        base = 44 + i * 20
        tag, offset, comp_len, orig_len, checksum = struct.unpack(">4sIIII", data[base:base + 20])
        entries.append((tag, offset, comp_len, orig_len, checksum))

    # sfnt search parameters
    entry_selector = max(num_tables.bit_length() - 1, 0)
    search_range = (2 ** entry_selector) * 16
    out = bytearray(struct.pack(">4sHHHH", flavor, num_tables, search_range,
                                entry_selector, num_tables * 16 - search_range))

    table_data, offset_cursor = [], 12 + num_tables * 16
    records = bytearray()
    for tag, offset, comp_len, orig_len, checksum in sorted(entries):
        raw = data[offset:offset + comp_len]
        body = raw if comp_len == orig_len else zlib.decompress(raw)
        records += struct.pack(">4sIII", tag, checksum, offset_cursor, orig_len)
        padded = body + b"\x00" * (-len(body) % 4)
        table_data.append(padded)
        offset_cursor += len(padded)
    return bytes(out + records + b"".join(table_data))


def load_font(size: int) -> ImageFont.FreeTypeFont:
    if not WOFF.exists():
        raise SystemExit(f"Missing {WOFF}. Run `npm install` first.")
    return ImageFont.truetype(io.BytesIO(woff_to_sfnt(WOFF.read_bytes())), size)


def render(px: int, *, safe: float = 1.0) -> Image.Image:
    """Render one square icon. `safe` shrinks the artwork into the centre for
    maskable icons, where Android may crop up to 20% off every edge."""
    img = Image.new("RGBA", (px, px), GROUND)
    draw = ImageDraw.Draw(img)
    inner = px * safe
    pad = (px - inner) / 2

    # Blueprint corner marks: hairline L's, the motif used across the UI.
    arm = inner * 0.17
    weight = max(1, round(px * 0.018))
    edge = pad + inner * 0.11
    far = px - edge
    mark = (242, 242, 243, 130)
    for x0, y0, x1, y1 in (
        (edge, edge, edge + arm, edge), (edge, edge, edge, edge + arm),
        (far - arm, edge, far, edge), (far, edge, far, edge + arm),
        (edge, far - arm, edge, far), (edge, far, edge + arm, far),
        (far - arm, far, far, far), (far, far - arm, far, far),
    ):
        draw.line((x0, y0, x1, y1), fill=mark, width=weight)

    # Wordmark, optically centred on its own ink bounds rather than the font's
    # line box -- Barlow Condensed's ascent leaves it visibly high otherwise.
    font = load_font(max(8, round(inner * 0.46)))
    box = draw.textbbox((0, 0), WORDMARK, font=font)
    draw.text((px / 2 - (box[0] + box[2]) / 2, px / 2 - (box[1] + box[3]) / 2),
              WORDMARK, font=font, fill=INK)
    return img


def svg_source() -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512" role="img" aria-label="ICC">
  <!-- Editable source for the PWA icon set. Regenerate the PNGs with:
       .venv/bin/python scripts/build_pwa_icons.py
       Replace this file with official artwork to rebrand; nothing else changes. -->
  <rect width="512" height="512" fill="{GROUND}"/>
  <g stroke="{INK}" stroke-opacity=".51" stroke-width="9" fill="none">
    <path d="M56 56h87M56 56v87M456 56h-87M456 56v87M56 456h87M56 456v-87M456 456h-87M456 456v-87"/>
  </g>
  <text x="256" y="256" fill="{INK}" font-family="Barlow Condensed, Barlow, sans-serif"
        font-weight="700" font-size="235" text-anchor="middle" dominant-baseline="central"
        letter-spacing="4">{WORDMARK}</text>
</svg>
'''


def main() -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    (BRAND_DIR / "icon.svg").write_text(svg_source(), encoding="utf-8")

    written = []
    for name, px, safe in (
        ("icon-192.png", 192, 1.0),
        ("icon-512.png", 512, 1.0),
        ("icon-maskable-512.png", 512, 0.8),
        ("apple-touch-icon-180.png", 180, 1.0),
    ):
        path = BRAND_DIR / name
        render(px, safe=safe).save(path, optimize=True)
        written.append(path)

    ico = BRAND_DIR / "favicon.ico"
    render(256).save(ico, sizes=[(16, 16), (32, 32), (48, 48)])
    written.append(ico)

    for path in [BRAND_DIR / "icon.svg", *written]:
        print(f"  {path.relative_to(ROOT)}  {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
