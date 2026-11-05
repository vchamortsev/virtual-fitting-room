"""Ролик для первого экрана: слева сайт, справа магазин, финал схлопывается в одну вещь."""

import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(r"C:\Users\User\.cursor\projects\c-projects-ai-learning-1-txt\assets")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "static" / "references" / "story.mp4"

W, H, FPS = 1920, 1080, 30
HALF = W // 2
GAP = 8
LABEL = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 28)

BEATS = (
    ("story-02-site.jpg", "story-01-store.jpg", 2.5, 0.40, 0.55, 0.35, 0.32),
    ("story-04-upload.jpg", "story-03-room.jpg", 2.5, 0.48, 0.48, 0.32, 0.30),
    ("story-09-screen.jpg", "story-05-exit.jpg", 3.3, 0.70, 0.46, 0.12, 0.28),
)
COURIER = ASSETS / "story-07-courier.jpg"
FINALE = ASSETS / "story-08-home.jpg"


def cover(path: Path, width: int, height: int, zoom: float, pan: float, focus_y: float = 0.35) -> Image.Image:
    image = Image.open(path).convert("RGB")
    scale = max(width / image.width, height / image.height) * zoom
    resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.BICUBIC)
    left = int((resized.width - width) * pan)
    top = int((resized.height - height) * focus_y)
    return resized.crop((left, max(0, top), left + width, max(0, top) + height))


def stamp(frame: Image.Image, text: str, x: int) -> None:
    draw = ImageDraw.Draw(frame)
    draw.text((x + 2, 42), text, font=LABEL, fill=(0, 0, 0))
    draw.text((x, 40), text, font=LABEL, fill=(255, 255, 255))


def split_frame(
    left: Path,
    right: Path,
    zoom: float,
    left_pan: float,
    right_pan: float,
    left_focus: float = 0.35,
    right_focus: float = 0.35,
) -> Image.Image:
    frame = Image.new("RGB", (W, H), (255, 255, 255))
    pane = (W - GAP) // 2
    frame.paste(cover(left, pane, H, zoom, left_pan, left_focus), (0, 0))
    frame.paste(cover(right, pane, H, zoom, right_pan, right_focus), (pane + GAP, 0))
    stamp(frame, "НА САЙТЕ", 48)
    stamp(frame, "В МАГАЗИНЕ", pane + GAP + 48)
    return frame


def full_frame(path: Path, zoom: float, pan: float, label: str | None = None) -> Image.Image:
    frame = cover(path, W, H, zoom, pan)
    if label:
        stamp(frame, label, 48)
    return frame


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-y",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}",
        "-r", str(FPS),
        "-i", "-",
        "-an",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(OUT),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    assert process.stdin is not None
    opening = None
    previous = None
    fade = int(0.35 * FPS)
    for left, right, seconds, left_pan, right_pan, left_focus, right_focus in BEATS:
        count = int(seconds * FPS)
        for index in range(count):
            progress = index / max(count - 1, 1)
            shot = split_frame(
                ASSETS / left,
                ASSETS / right,
                1.0 + 0.03 * progress,
                left_pan,
                right_pan,
                left_focus,
                right_focus,
            )
            if opening is None:
                opening = shot
            if previous is not None and index < fade:
                shot = Image.blend(previous, shot, index / fade)
            process.stdin.write(shot.tobytes())
        previous = shot
    delivery = full_frame(COURIER, 1.0, 0.5, "ДОСТАВКА")
    for index in range(int(2.6 * FPS)):
        shot = delivery if index >= fade else Image.blend(previous, delivery, (index + 1) / fade)
        process.stdin.write(shot.tobytes())
    previous = delivery
    ending = full_frame(FINALE, 1.0, 0.5)
    collapse = int(0.7 * FPS)
    hold = int(3.2 * FPS)
    for index in range(collapse + hold):
        if index < collapse:
            shot = Image.blend(previous, ending, (index + 1) / collapse)
        else:
            shot = full_frame(FINALE, 1.0 + 0.03 * ((index - collapse) / max(hold - 1, 1)), 0.5)
        process.stdin.write(shot.tobytes())
    previous = shot
    assert opening is not None
    for index in range(fade):
        shot = Image.blend(previous, opening, (index + 1) / fade)
        process.stdin.write(shot.tobytes())
    process.stdin.close()
    code = process.wait()
    if code != 0:
        raise SystemExit(code)
    print(OUT, OUT.stat().st_size)


if __name__ == "__main__":
    main()
