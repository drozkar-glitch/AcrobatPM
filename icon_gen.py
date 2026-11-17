# STAVITEL_WIN_APP: AcrobatPM
# © 2026 Created by Pavel Mareš
import os
from PIL import Image, ImageDraw, ImageFilter


def generate_3d_app_icon(out_dir: str = "assets") -> str:
    os.makedirs(out_dir, exist_ok=True)
    size = 512
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # 1. Měkký vrhaný stín pod hlavní 3D dlaždicí
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle([44, 58, 468, 482], radius=104, fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas = Image.alpha_composite(canvas, shadow)

    # 2. Spodní 3D hrana základny (tmavý ocelový objem)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle([38, 46, 474, 476], radius=104, fill=(9, 14, 28, 255))

    # 3. Hlavní tělo ikony s prostorovým přechodem
    body = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    b_px = body.load()
    for y in range(34, 462):
        t = (y - 34) / 428.0
        r = int(30 * (1 - t) + 13 * t)
        g = int(45 * (1 - t) + 21 * t)
        b = int(78 * (1 - t) + 40 * t)
        for x in range(38, 474):
            b_px[x, y] = (r, g, b, 255)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([38, 34, 474, 462], radius=104, fill=255)
    body.putalpha(mask)
    canvas = Image.alpha_composite(canvas, body)

    # Horní jemný odlesk hrany základny
    rim = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    r_draw = ImageDraw.Draw(rim)
    r_draw.rounded_rectangle([41, 37, 471, 459], radius=101, outline=(125, 211, 252, 95), width=4)
    canvas = Image.alpha_composite(canvas, rim)

    # 4. Stín pod dokumentem uvnitř bezpečné zóny
    doc_shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ds_draw = ImageDraw.Draw(doc_shadow)
    ds_draw.rounded_rectangle([122, 108, 382, 412], radius=38, fill=(0, 0, 0, 145))
    doc_shadow = doc_shadow.filter(ImageFilter.GaussianBlur(14))
    canvas = Image.alpha_composite(canvas, doc_shadow)

    # 5. Bílý 3D list dokumentu + spodní hrana papíru
    d_draw = ImageDraw.Draw(canvas)
    d_draw.rounded_rectangle([118, 98, 378, 404], radius=36, fill=(203, 213, 225, 255))
    d_draw.rounded_rectangle([118, 88, 378, 394], radius=36, fill=(248, 250, 252, 255))

    # Červený 3D PDF štítek v horní části listu
    d_draw.rounded_rectangle([94, 132, 298, 218], radius=24, fill=(153, 27, 27, 255))
    d_draw.rounded_rectangle([94, 124, 298, 210], radius=24, fill=(220, 38, 38, 255))
    d_draw.rounded_rectangle([102, 130, 290, 164], radius=16, fill=(252, 165, 165, 70))

    # Tři čisté grafické pruhy představující PDF křivky/symbol (bez písmen)
    d_draw.rounded_rectangle([124, 152, 174, 182], radius=9, fill=(255, 255, 255, 245))
    d_draw.rounded_rectangle([188, 152, 232, 182], radius=9, fill=(255, 255, 255, 225))
    d_draw.rounded_rectangle([246, 152, 272, 182], radius=9, fill=(255, 255, 255, 200))

    # Řádky textu na papíru
    d_draw.rounded_rectangle([148, 244, 344, 264], radius=10, fill=(100, 116, 139, 220))
    d_draw.rounded_rectangle([148, 284, 344, 304], radius=10, fill=(148, 163, 184, 220))
    d_draw.rounded_rectangle([148, 324, 276, 344], radius=10, fill=(148, 163, 184, 220))

    # 6. 3D editační pero vpravo dole
    pen_shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(pen_shadow).polygon(
        [(286, 376), (318, 408), (426, 300), (394, 268)], fill=(0, 0, 0, 140)
    )
    pen_shadow = pen_shadow.filter(ImageFilter.GaussianBlur(9))
    canvas = Image.alpha_composite(canvas, pen_shadow)

    d_draw = ImageDraw.Draw(canvas)
    d_draw.polygon([(284, 366), (318, 400), (428, 290), (394, 256)], fill=(2, 132, 199, 255))
    d_draw.polygon([(284, 366), (301, 383), (411, 273), (394, 256)], fill=(56, 189, 248, 255))
    d_draw.polygon([(284, 366), (318, 400), (266, 418)], fill=(251, 191, 36, 255))
    d_draw.polygon([(274, 392), (291, 409), (266, 418)], fill=(15, 23, 42, 255))

    final_256 = canvas.resize((256, 256), Image.Resampling.LANCZOS)
    png_path = os.path.join(out_dir, "icon.png")
    ico_path = os.path.join(out_dir, "app.ico")
    final_256.save(png_path, format="PNG")
    final_256.save(
        ico_path,
        format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
    )
    return ico_path


if __name__ == "__main__":
    generate_3d_app_icon()
