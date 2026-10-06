"""Author original M2O procedural studio loops; no downloaded visual assets.

Requires Pillow, NumPy and an FFmpeg executable on this authoring machine only.
The frontend ships the MP4/WebP artwork, never the authoring runtime or encoder.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

WIDTH, HEIGHT, FPS, SECONDS = 640, 480, 24, 6
PALETTES = {
    "engineering": ((239, 227, 255), (138, 85, 241), (43, 38, 154), (134, 231, 255)),
    "hr": ((255, 223, 235), (244, 113, 162), (156, 50, 112), (255, 197, 142)),
    "finance": ((220, 248, 234), (50, 190, 149), (12, 107, 92), (255, 219, 113)),
}


def blend(first, second, amount):
    return tuple(round(a * (1 - amount) + b * amount) for a, b in zip(first, second))


def sphere(radius, color):
    axis = np.linspace(-1, 1, radius * 2 + 2)
    x, y = np.meshgrid(axis, axis)
    z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
    diffuse = np.clip(-0.45 * x - 0.55 * y + 0.7 * z, 0, 1)
    specular = np.clip(-0.3 * x - 0.4 * y + 0.86 * z, 0, 1) ** 34
    pixels = np.zeros((*x.shape, 4), dtype=np.uint8)
    for channel, base in enumerate(color):
        pixels[:, :, channel] = np.clip(base * (0.38 + 0.58 * diffuse) + 110 * specular, 0, 255)
    pixels[:, :, 3] = np.clip((1 - x * x - y * y) * radius * 4, 0, 1) * 255
    return Image.fromarray(pixels)


def torus(draw, center, phase, color, highlight, tilt, radius=115, tube=19):
    """Projected shaded torus, painter-sorted by depth."""
    faces = []
    def point(theta, phi):
        x = (radius + tube * math.cos(phi)) * math.cos(theta)
        y = (radius + tube * math.cos(phi)) * math.sin(theta)
        z = tube * math.sin(phi)
        rotated_y = y * math.cos(tilt) - z * math.sin(tilt)
        depth = y * math.sin(tilt) + z * math.cos(tilt)
        rotation = 0.18 * math.sin(phase)
        return (center[0] + x * math.cos(rotation) - rotated_y * math.sin(rotation), center[1] + x * math.sin(rotation) + rotated_y * math.cos(rotation), depth)
    for i in range(48):
        theta = math.tau * i / 48
        for j in range(12):
            phi = math.tau * j / 12
            points = [point(theta, phi), point(theta + math.tau / 48, phi), point(theta + math.tau / 48, phi + math.tau / 12), point(theta, phi + math.tau / 12)]
            light = max(0, 0.4 + 0.4 * math.cos(phi - 1) - 0.2 * math.sin(theta))
            faces.append((sum(p[2] for p in points), [(p[0], p[1]) for p in points], blend(color, highlight, light)))
    for _, polygon, shade in sorted(faces, key=lambda face: face[0]):
        draw.polygon(polygon, fill=shade)


def backdrop(palette):
    light, bright, deep, accent = palette
    y, x = np.mgrid[0:HEIGHT, 0:WIDTH]
    fade = np.clip((x / WIDTH + y / HEIGHT) * 0.3, 0, 1)
    glow = np.exp(-((x - 480) ** 2 + (y - 110) ** 2) / 85000)
    noise = np.random.default_rng(26).normal(0, 0.65, (HEIGHT, WIDTH))
    pixels = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    for channel in range(3):
        pixels[:, :, channel] = np.clip(light[channel] * (1 - fade) + blend(light, bright, 0.15)[channel] * fade + glow * (accent[channel] - light[channel]) * 0.25 + noise, 0, 255)
    image = Image.fromarray(pixels)
    draw = ImageDraw.Draw(image)
    line = blend(light, deep, 0.08)
    for row in range(335, HEIGHT, 24):
        draw.line((0, row, WIDTH, row), fill=line)
    for column in range(-WIDTH, WIDTH * 2, 80):
        draw.line((WIDTH / 2, 240, column, HEIGHT), fill=line)
    return image


def frame(base, palette, department, phase, objects):
    image = base.copy().convert("RGBA")
    _, bright, deep, accent = palette
    bob = 10 * math.sin(phase)
    shadow = Image.new("RGBA", image.size)
    draw_shadow = ImageDraw.Draw(shadow)
    draw_shadow.ellipse((150, 335, 490, 382), fill=(*deep, 38))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(15)))
    draw = ImageDraw.Draw(image)
    if department == "hr":
        draw.line((245, 216 + bob, 409, 231 - bob), fill=(*deep, 120), width=12)
        image.alpha_composite(objects[0], (151, round(123 + bob)))
        image.alpha_composite(objects[1], (359, round(175 - bob)))
        torus(draw, (315, 308 + bob / 2), phase, bright, (255, 250, 251), 0.95, 98, 15)
    elif department == "finance":
        for index in range(3):
            torus(draw, (320, 293 - index * 42 + bob), phase + index * 0.15, deep if index == 0 else bright, accent, 1.0, 112, 15)
        image.alpha_composite(objects[1], (408, round(105 - bob)))
    else:
        torus(draw, (306, 230 + bob), phase, deep, accent, 0.87, 132, 18)
        image.alpha_composite(objects[0], (214, round(128 + bob)))
        x, y = 450 + 6 * math.cos(phase), 299 - bob
        draw.polygon([(x, y - 35), (x + 44, y - 18), (x + 6, y + 1), (x - 35, y - 17)], fill=accent)
        draw.polygon([(x - 35, y - 17), (x + 6, y + 1), (x + 6, y + 46), (x - 35, y + 25)], fill=bright)
        draw.polygon([(x + 6, y + 1), (x + 44, y - 18), (x + 44, y + 26), (x + 6, y + 46)], fill=deep)
    draw = ImageDraw.Draw(image)
    for i, (x, y, width) in enumerate([(88, 112, 79), (451, 365, 83), (485, 79, 50)]):
        drift = math.sin(phase + i * 1.1) * 8
        draw.rounded_rectangle((x + 3, y + 6 + drift, x + width + 3, y + 36 + drift), radius=14, fill=deep)
        draw.rounded_rectangle((x, y + drift, x + width, y + 30 + drift), radius=14, fill=accent if i % 2 == 0 else bright, outline=(255, 255, 255), width=2)
    for x, y in [(115, 280), (519, 223), (354, 73)]:
        draw.regular_polygon((x, y + math.sin(phase) * 4, 8), 4, rotation=45, fill=deep)
    return image.convert("RGB")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", required=True, type=Path)
    args = parser.parse_args()
    encoder = args.ffmpeg.resolve(strict=True)
    output = Path(__file__).resolve().parents[1] / "public" / "scenes"
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"authorship": "Original M2O procedural geometry, lighting and seeded texture", "width": WIDTH, "height": HEIGHT, "fps": FPS, "seconds": SECONDS, "scenes": {}}
    for department, palette in PALETTES.items():
        movie, poster = output / f"{department}.mp4", output / f"{department}.webp"
        if movie.exists() or poster.exists():
            raise FileExistsError(f"Refusing to overwrite existing scene: {department}")
        base = backdrop(palette)
        objects = [sphere(90, palette[1]), sphere(56, palette[3])]
        frame(base, palette, department, 0, objects).save(poster, quality=86)
        command = [str(encoder), "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{WIDTH}x{HEIGHT}", "-framerate", str(FPS), "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-map_metadata", "-1", str(movie)]
        with subprocess.Popen(command, stdin=subprocess.PIPE) as process:
            for index in range(FPS * SECONDS):
                process.stdin.write(frame(base, palette, department, math.tau * index / (FPS * SECONDS), objects).tobytes())
            process.stdin.close()
            if process.wait() != 0:
                raise RuntimeError(f"Encoding failed: {department}")
        sizes = {path.suffix[1:]: path.stat().st_size for path in (movie, poster)}
        if sizes["mp4"] > 1_500_000 or sizes["webp"] > 120_000:
            raise ValueError(f"Scene exceeds transfer budget: {sizes}")
        manifest["scenes"][department] = {"bytes": sizes, "sha256": hashlib.sha256(movie.read_bytes()).hexdigest()}
        print(department, sizes)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
