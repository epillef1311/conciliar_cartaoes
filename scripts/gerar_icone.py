"""Converte a logo oficial em ícone Windows com todos os tamanhos necessários."""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "frigorifico-candeias-logo-cortada.png"
TARGET = ROOT / "assets" / "frigorifico-candeias.ico"


def main() -> None:
    with Image.open(SOURCE) as image:
        image.convert("RGBA").save(
            TARGET,
            format="ICO",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )


if __name__ == "__main__":
    main()
