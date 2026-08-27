# -*- coding: utf-8 -*-
"""
Генератор иконки Downloader3000 (app.ico).
Цвета — те же, что в index.html и в самой программе.
Запуск:  python make_icon.py
"""
import os
from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")

S = 1024                      # рисуем крупно, потом уменьшаем — так получается сглаживание
BG1 = (0x0f, 0x0c, 0x29)      # #0f0c29
BG2 = (0x30, 0x2b, 0x63)      # #302b63
BG3 = (0x24, 0x24, 0x3e)      # #24243e
GOLD_A = (0xf7, 0x97, 0x1e)   # #f7971e
GOLD_B = (0xff, 0xd2, 0x00)   # #ffd200


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def diagonal_gradient(size, stops):
    """linear-gradient(135deg, ...) — цвет зависит от (x+y)."""
    img = Image.new("RGB", (size, size))
    px = img.load()
    n = len(stops) - 1
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2.0 * (size - 1))
            seg = min(int(t * n), n - 1)
            local = t * n - seg
            px[x, y] = lerp(stops[seg], stops[seg + 1], local)
    return img


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def main():
    bg = diagonal_gradient(S, [BG1, BG2, BG3])
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(bg, (0, 0), rounded_mask(S, int(S * 0.22)))

    # золотая заливка для стрелки
    gold = Image.new("RGB", (S, S))
    gpx = gold.load()
    for y in range(S):
        for x in range(S):
            gpx[x, y] = lerp(GOLD_A, GOLD_B, (x + y) / (2.0 * (S - 1)))

    # маска: стрелка вниз + «полка» под ней (классический значок загрузки)
    shape = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(shape)
    cx = S // 2
    stem_w = int(S * 0.135)
    d.rectangle([cx - stem_w // 2, int(S * 0.20), cx + stem_w // 2, int(S * 0.545)], fill=255)
    d.polygon([(cx - int(S * 0.235), int(S * 0.50)),
               (cx + int(S * 0.235), int(S * 0.50)),
               (cx, int(S * 0.755))], fill=255)
    tray_y = int(S * 0.795)
    d.rounded_rectangle([int(S * 0.235), tray_y, int(S * 0.765), tray_y + int(S * 0.075)],
                        radius=int(S * 0.037), fill=255)

    icon.paste(gold, (0, 0), shape)

    # тонкая светлая рамка — как border: 1px rgba(255,255,255,.1)
    edge = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(edge).rounded_rectangle(
        [2, 2, S - 3, S - 3], radius=int(S * 0.22), outline=(255, 255, 255, 46), width=6)
    icon = Image.alpha_composite(icon, edge)

    # .ico — для окна и ярлыка на Windows
    sizes = [256, 128, 64, 48, 32, 24, 16]
    frames = [icon.resize((s, s), Image.LANCZOS) for s in sizes]
    frames[0].save(OUT, format="ICO", sizes=[(s, s) for s in sizes])
    print("icon ->", OUT, os.path.getsize(OUT), "bytes")

    # .png — из него flet build делает иконки под все платформы,
    # включая адаптивную иконку Android. 1024x1024 — требование сборщика.
    assets = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "assets")
    os.makedirs(assets, exist_ok=True)
    png = os.path.join(assets, "icon.png")
    icon.save(png, format="PNG")
    print("icon ->", png, os.path.getsize(png), "bytes")


if __name__ == "__main__":
    main()
