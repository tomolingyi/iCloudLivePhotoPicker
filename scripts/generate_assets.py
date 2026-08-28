from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "src" / "icloud_live_picker" / "assets"


def build_icon() -> Image.Image:
    scale = 4
    size = 256 * scale
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (12 * scale, 12 * scale, 244 * scale, 244 * scale),
        radius=68 * scale,
        fill="#278B82",
    )
    cloud = "#FFFFFF"
    draw.ellipse((57 * scale, 101 * scale, 137 * scale, 181 * scale), fill=cloud)
    draw.ellipse((98 * scale, 69 * scale, 184 * scale, 170 * scale), fill=cloud)
    draw.ellipse((151 * scale, 106 * scale, 211 * scale, 174 * scale), fill=cloud)
    draw.rounded_rectangle(
        (57 * scale, 124 * scale, 211 * scale, 181 * scale),
        radius=27 * scale,
        fill=cloud,
    )

    accent = "#278B82"
    draw.rounded_rectangle(
        (121 * scale, 122 * scale, 154 * scale, 155 * scale),
        radius=8 * scale,
        fill=accent,
    )
    draw.ellipse((129 * scale, 130 * scale, 146 * scale, 147 * scale), fill=cloud)
    return image.resize((256, 256), Image.Resampling.LANCZOS)


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    icon = build_icon()
    icon.save(ASSET_DIR / "app-icon.png", optimize=True)
    icon.save(
        ASSET_DIR / "app-icon.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    main()
