"""Generate the display sizes the UI actually asks for, from the master logos.

The app shipped a single 512x512 PNG (182 KB) that was rendered at 28x28 px
in the sidebar and as the favicon, plus a 1024x1024 (838 KB) copy for the
public site. Both were on the critical path of every authenticated page.

Usage:  python scripts/build_images.py
"""
from __future__ import annotations

import pathlib

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent

# (source, destination, longest edge)
DERIVED = [
    ('static/image/logo.png', 'static/image/logo-32.png', 32),
    ('static/image/logo.png', 'static/image/logo-64.png', 64),
    ('static/image/logo.png', 'static/image/logo-180.png', 180),
    ('static/image/logo.png', 'static/image/logo-256.png', 256),
    ('static/public/image/logo.png', 'static/public/image/logo-256.png', 256),
    ('static/public/image/logo.png', 'static/public/image/logo-512.png', 512),
]


def build(src: pathlib.Path, dst: pathlib.Path, edge: int) -> tuple[int, int]:
    with Image.open(src) as image:
        image = image.convert('RGBA')
        resized = image.resize(
            (edge, edge), Image.LANCZOS
        ) if image.size == (edge, edge) else _fit(image, edge)

        # Keep the alpha channel: the masters have a transparent surround.
        resized.save(dst, format='PNG', optimize=True)

        # A tiny, fully-opaque-on-white copy is what the favicon actually
        # needs; browsers upsample favicons anyway and PNG-with-alpha at 32px
        # costs noticeably more than the reduced palette.
        if edge <= 32:
            flat = Image.new('RGB', resized.size, (255, 255, 255))
            flat.paste(resized, mask=resized.split()[3])
            flat.quantize(colors=64, method=Image.MEDIANCUT).save(
                dst, format='PNG', optimize=True
            )

    return dst.stat().st_size, src.stat().st_size


def _fit(image: Image.Image, edge: int) -> Image.Image:
    width, height = image.size
    if width == height:
        return image.resize((edge, edge), Image.LANCZOS)
    scale = edge / max(width, height)
    return image.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS)


def main() -> None:
    for rel_src, rel_dst, edge in DERIVED:
        src = ROOT / rel_src
        dst = ROOT / rel_dst
        if not src.exists():
            print(f'skip (missing source): {rel_src}')
            continue
        out_bytes, src_bytes = build(src, dst, edge)
        print(
            f'{rel_dst:<42} {edge:>4}px  '
            f'{src_bytes / 1024:7.1f} KB -> {out_bytes / 1024:6.1f} KB'
        )


if __name__ == '__main__':
    main()
