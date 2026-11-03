# -*- coding: utf-8 -*-
"""生成 assets/app.ico（多尺寸）。用法：python assets/gen_icon.py"""
import os

from PIL import Image, ImageDraw

SS = 8  # 超采样倍数，先大图再缩小，边缘更干净


def rounded(size, radius, fill):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=fill)
    return im


def gradient(size, top, bottom):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for y in range(size):
        t = y / (size - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (size, y)], fill=c + (255,))
    return im


def build(px=1024):
    S = px * SS

    # 圆角底 + 垂直渐变
    mask = rounded(S, int(S * 0.235), (255, 255, 255, 255)).split()[3]
    base = gradient(S, (108, 112, 246), (67, 56, 202))
    base.putalpha(mask)

    d = ImageDraw.Draw(base)

    # 轻微高光，避免大面积死板
    hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dh = ImageDraw.Draw(hl)
    dh.ellipse([-S * 0.35, -S * 0.62, S * 1.05, S * 0.30], fill=(255, 255, 255, 26))
    base = Image.alpha_composite(base, hl)
    d = ImageDraw.Draw(base)

    # 对话气泡
    bx0, by0, bx1, by1 = S * 0.185, S * 0.245, S * 0.815, S * 0.685
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=int(S * 0.105), fill=(255, 255, 255, 255))
    # 气泡尾巴
    d.polygon([
        (S * 0.335, by1 - S * 0.005),
        (S * 0.300, S * 0.775),
        (S * 0.470, by1 - S * 0.005),
    ], fill=(255, 255, 255, 255))

    # 三个点（省略号），表示自动应答
    cy = (by0 + by1) / 2
    r = S * 0.031
    for i, cx in enumerate((0.345, 0.500, 0.655)):
        d.ellipse([S * cx - r, cy - r, S * cx + r, cy + r], fill=(79, 70, 229, 255))

    # 右下闪电，强调「秒回」
    bolt = [
        (0.735, 0.560), (0.815, 0.560), (0.770, 0.660),
        (0.845, 0.660), (0.720, 0.815), (0.752, 0.700), (0.690, 0.700),
    ]
    d.polygon([(S * x, S * y) for x, y in bolt], fill=(250, 204, 21, 255))

    return base.resize((px, px), Image.LANCZOS)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    img = build(256)
    out = os.path.join(here, "app.ico")
    img.save(out, format="ICO",
             sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    img.save(os.path.join(here, "app.png"))
    print("saved", out, os.path.getsize(out))


if __name__ == "__main__":
    main()
