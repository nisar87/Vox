"""Draw the Vox icon (packaging/vox.ico) so no binary file lives in the repo."""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8, 8, SIZE - 8, SIZE - 8), radius=64, fill=(52, 46, 204, 255))
for x, height in ((76, 56), (110, 112), (144, 152), (178, 72)):
    draw.rounded_rectangle((x - 12, SIZE // 2 - height // 2, x + 12, SIZE // 2 + height // 2), radius=12, fill="white")
target = Path(__file__).parent / "vox.ico"
image.save(target, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"wrote {target}")
