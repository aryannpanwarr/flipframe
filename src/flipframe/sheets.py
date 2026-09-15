"""Step 4: tile frames into labeled 3x3 contact sheets."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CELL_W, CELL_H, GRID = 512, 288, 3


def stamp(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def seconds_of(frame: Path) -> int:
    return int(frame.stem)


def build(frames: list[Path], out: Path) -> list[tuple[Path, list[int]]]:
    """Return (sheet_path, seconds_on_sheet) for each sheet."""
    out.mkdir(exist_ok=True)
    font = ImageFont.load_default(size=26)
    per = GRID * GRID
    sheets = []
    for i in range(0, len(frames), per):
        batch = frames[i:i + per]
        rows = -(-len(batch) // GRID)
        sheet = Image.new("RGB", (CELL_W * GRID, CELL_H * rows), "black")
        draw = ImageDraw.Draw(sheet)
        for j, f in enumerate(batch):
            x, y = (j % GRID) * CELL_W, (j // GRID) * CELL_H
            img = Image.open(f).convert("RGB")
            img.thumbnail((CELL_W, CELL_H))
            sheet.paste(img, (x + (CELL_W - img.width) // 2, y + (CELL_H - img.height) // 2))
            label = stamp(seconds_of(f))
            box = draw.textbbox((x + 6, y + 6), label, font=font)
            draw.rectangle((box[0] - 4, box[1] - 3, box[2] + 4, box[3] + 3), fill="black")
            draw.text((x + 6, y + 6), label, font=font, fill="yellow")
        path = out / f"sheet_{i // per:03d}.jpg"
        sheet.save(path, quality=85)
        sheets.append((path, [seconds_of(f) for f in batch]))
    return sheets
