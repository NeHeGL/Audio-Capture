#!/usr/bin/env python3
"""Generate icon.png and icon.ico for Audio Capture (dark UI + loopback motif)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
RADIUS = 200

BG = (35, 39, 46, 255)
BLUE = (31, 106, 165, 255)
BLUE_LIGHT = (61, 149, 214, 255)
RED = (192, 57, 43, 255)
WAVE = (52, 152, 219, 255)


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def draw_icon(size: int = SIZE) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    pad = int(size * 0.08)
    draw.rounded_rectangle([pad, pad, size - pad, size - pad], radius=int(size * 0.19), fill=BG)

    cx = size // 2
    cy = size // 2 + int(size * 0.04)

    # Loopback arc (speaker output → capture)
    arc_box = [int(size * 0.12), int(size * 0.1), int(size * 0.88), int(size * 0.9)]
    draw.arc(arc_box, start=300, end=120, fill=BLUE_LIGHT, width=int(size * 0.045))
    ax, ay = int(size * 0.78), int(size * 0.22)
    aw = int(size * 0.11)
    draw.polygon(
        [(ax, ay), (ax - aw, ay - aw // 2), (ax - aw, ay + aw // 2)],
        fill=BLUE_LIGHT,
    )

    # Speaker body
    sp_w = int(size * 0.36)
    sp_h = int(size * 0.42)
    left = cx - sp_w // 2 - int(size * 0.08)
    top = cy - sp_h // 2
    draw.rounded_rectangle(
        [left, top, left + sp_w, top + sp_h],
        radius=int(size * 0.06),
        fill=BLUE,
    )
    # cone
    draw.polygon(
        [
            (left + sp_w, cy - sp_h // 3),
            (left + sp_w + int(size * 0.14), cy - int(size * 0.18)),
            (left + sp_w + int(size * 0.14), cy + int(size * 0.18)),
            (left + sp_w, cy + sp_h // 3),
        ],
        fill=BLUE,
    )

    # Sound waves
    for i, expand in enumerate((0.12, 0.2, 0.28)):
        x0 = left + sp_w + int(size * (0.17 + expand))
        draw.arc(
            [x0, cy - int(size * 0.22), x0 + int(size * 0.18), cy + int(size * 0.22)],
            start=300,
            end=60,
            fill=BLUE_LIGHT if i < 2 else WAVE,
            width=max(3, int(size * 0.022)),
        )

    # Waveform strip (trim timeline echo)
    wy = cy + int(size * 0.26)
    wx0 = int(size * 0.2)
    wx1 = int(size * 0.8)
    points: list[tuple[int, int]] = []
    steps = 40
    import math

    for i in range(steps + 1):
        t = i / steps
        x = wx0 + int((wx1 - wx0) * t)
        y = wy + int(math.sin(t * math.pi * 6) * size * 0.045 + math.sin(t * math.pi * 14) * size * 0.02)
        points.append((x, y))
    draw.line(points, fill=WAVE, width=max(3, int(size * 0.028)), joint="curve")

    # Record dot
    r = int(size * 0.045)
    draw.ellipse([int(size * 0.18) - r, int(size * 0.2) - r, int(size * 0.18) + r, int(size * 0.2) + r], fill=RED)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(layer, mask=rounded_mask(size, RADIUS))
    return canvas


def build_ico(png_path: Path, ico_path: Path) -> None:
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    src = Image.open(png_path).convert("RGBA")
    src.save(ico_path, format="ICO", sizes=sizes)


def main() -> None:
    root = Path(__file__).resolve().parent
    img = draw_icon()
    png_path = root / "icon.png"
    ico_path = root / "icon.ico"
    img.save(png_path)
    print(f"Saved {png_path.name}")
    build_ico(png_path, ico_path)
    print(f"Saved {ico_path.name}")


if __name__ == "__main__":
    main()