"""Prepara uma cópia recortada da logo, sem alterar o PNG original fornecido."""

from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "frigorifico-candeias-logo.png"
TARGET = ROOT / "assets" / "frigorifico-candeias-logo-cortada.png"


def main() -> None:
    with Image.open(SOURCE) as source:
        image = source.convert("RGBA")
        if "A" in source.getbands():
            bbox = image.getchannel("A").getbbox()
        else:
            background = Image.new("RGB", image.size, "white")
            difference = ImageChops.difference(image.convert("RGB"), background)
            bbox = difference.point(lambda value: 255 if value > 12 else 0).getbbox()
        if bbox is None:
            raise ValueError("a logo não contém pixels diferentes do fundo branco")
        padding = 24
        left, top, right, bottom = bbox
        crop = image.crop(
            (
                max(0, left - padding),
                max(0, top - padding),
                min(image.width, right + padding),
                min(image.height, bottom + padding),
            )
        )
        crop.save(TARGET, format="PNG", optimize=True)


if __name__ == "__main__":
    main()
