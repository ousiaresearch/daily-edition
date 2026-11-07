#!/usr/bin/env python3.14
"""Compose the Daily Edition hero: a generated print still life plus vector typography.

Route (a) of the branded-card procedure: the raster carries the argument with no legible text, and
every word is vector type laid over it, with the print's own defect echoed (a second plate landing a
hair off) so the type reads as printed rather than pasted.

Two canvases come out of one brief:

    1600x900   16:9  README hero
    1600x800    2:1  catalog card (the entry's `image:` field is specified at 2:1)

    python3.14 docs/hero/build.py [--background PATH]

Sources kept beside the output: `prompt.txt` (the generation brief) and this script.
"""

import argparse
import base64
import pathlib
import sys

import resvg_py
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent

ZOOM = 1.08
CREAM = '#F0E7D4'
BODY = '#E2D6BF'
VERMILION = '#C4553C'
SERIF = "'Iowan Old Style', 'Palatino Linotype', Palatino, Baskerville, 'Times New Roman', serif"
SANS = "'Helvetica Neue', Helvetica, Arial, sans-serif"

# Vertical anchors as a fraction of the canvas height, so one composition serves both ratios.
ANCHORS = {
    'label': 0.218, 'rule1': 0.240, 'display1': 0.367, 'display2': 0.494,
    'rule2': 0.547, 'phrase': 0.613, 'question': 0.664,
    'foot1': 0.906, 'foot2': 0.945,
}

COPY = {
    'label': 'OUSIA RESEARCH',
    'name': ['Daily', 'Edition'],
    'phrase': 'Every story once.',
    'question': 'What would you read if the paper ended?',
    'footer': ['HERMES DESKTOP PLUGIN', 'github.com/ousiaresearch/daily-edition'],
}


def data_uri(path: pathlib.Path) -> str:
    return 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')


def press(source: pathlib.Path) -> pathlib.Path:
    """Pull the raster back onto paper.

    The generation leaves one saturated vermilion band along the finished page's edge that reads as a
    screen glow rather than an ink. Desaturate only those pixels, toward the muted ink in the palette,
    and cache the result so the raw generation stays as the source of record.
    """
    import numpy as np

    target = source.with_name(source.stem + '-pressed.png')
    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
        return target

    pixels = np.asarray(Image.open(source).convert('RGB')).astype(float)
    r, g, b = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]
    hot = (r - np.maximum(g, b) > 45) & (r > 90)
    grey = pixels.mean(axis=2, keepdims=True)
    muted = grey * np.array([1.06, 0.62, 0.55])  # warm ink, not a glow
    pixels[hot] = pixels[hot] * 0.35 + muted[hot] * 0.65
    Image.fromarray(pixels.clip(0, 255).astype('uint8')).save(target)
    return target


def esc(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def svg(background: pathlib.Path, width: int, height: int) -> str:
    k = height / 900.0                      # type scales with the canvas
    a = {name: round(f * height, 1) for name, f in ANCHORS.items()}
    label, name_lines, phrase = COPY['label'], COPY['name'], COPY['phrase']
    question, footer = COPY['question'], COPY['footer']
    display = round(104 * k, 1)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="scrim" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#120E0B" stop-opacity="0.80"/>
      <stop offset="0.30" stop-color="#120E0B" stop-opacity="0.58"/>
      <stop offset="0.46" stop-color="#120E0B" stop-opacity="0.20"/>
      <stop offset="0.60" stop-color="#120E0B" stop-opacity="0"/>
    </linearGradient>
    <filter id="grain" x="0" y="0" width="100%" height="100%">
      <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="7" result="noise"/>
      <feColorMatrix in="noise" type="saturate" values="0"/>
      <feComponentTransfer><feFuncA type="linear" slope="0.10"/></feComponentTransfer>
    </filter>
    <filter id="soften" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="0.9"/>
    </filter>
  </defs>

  <image href="{data_uri(background)}" x="{-(width * (ZOOM - 1) / 2) - 18:.1f}" y="{-(height * (ZOOM - 1) / 2):.1f}"
         width="{width * ZOOM:.1f}" height="{height * ZOOM:.1f}" preserveAspectRatio="xMidYMid slice"/>
  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#scrim)"/>
  <rect x="0" y="0" width="{width}" height="{height}" filter="url(#grain)" opacity="0.55"/>

  <g font-family="{SANS}">
    <text x="88" y="{a['label']}" fill="#D8664A" font-size="{round(19 * k, 1)}" letter-spacing="{round(6.6 * k, 2)}"
          font-weight="500">{esc(label)}</text>
    <rect x="88" y="{a['rule1']}" width="{round(224 * k, 1)}" height="1" fill="#8A7355" opacity="0.8"/>
  </g>

  <!-- the second plate: the same words in vermilion, a hair off, as a second print pass -->
  <g font-family="{SERIF}" font-size="{display}" fill="{VERMILION}" opacity="0.22" filter="url(#soften)">
    <text x="91" y="{round(a['display1'] - 3 * k, 1)}">{esc(name_lines[0])}</text>
    <text x="91" y="{round(a['display2'] - 3 * k, 1)}">{esc(name_lines[1])}</text>
  </g>
  <g font-family="{SERIF}" font-size="{display}" fill="{CREAM}" letter-spacing="-1">
    <text x="88" y="{a['display1']}">{esc(name_lines[0])}</text>
    <text x="88" y="{a['display2']}">{esc(name_lines[1])}</text>
  </g>

  <rect x="88" y="{a['rule2']}" width="{round(520 * k, 1)}" height="1" fill="#5A4A36" opacity="0.9"/>

  <g font-family="{SERIF}" font-size="{round(33 * k, 1)}" font-style="italic" fill="{BODY}">
    <text x="88" y="{a['phrase']}">{esc(phrase)}</text>
  </g>
  <g font-family="{SANS}" font-size="{round(23 * k, 1)}" fill="#CBBEA6" letter-spacing="0.4">
    <text x="88" y="{a['question']}">{esc(question)}</text>
  </g>

  <g font-family="{SANS}" fill="#C4B49B" letter-spacing="{round(2.8 * k, 2)}">
    <text x="88" y="{a['foot1']}" font-size="{round(18 * k, 1)}">{esc(footer[0])}</text>
    <text x="88" y="{a['foot2']}" letter-spacing="0.5" font-size="{round(21 * k, 1)}" fill="#D2C2A8">{esc(footer[1])}</text>
  </g>

  <!-- one grain field over everything, so the vector type shares the print's surface -->
  <rect x="0" y="0" width="{width}" height="{height}" filter="url(#grain)" opacity="0.16"/>
</svg>
"""


def render(background: pathlib.Path, out: pathlib.Path, width: int, height: int) -> None:
    source = svg(background, width, height)
    png = bytes(resvg_py.svg_to_bytes(svg_string=source, width=width, height=height))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    jpg = out.with_suffix('.jpg')
    Image.open(out).convert('RGB').save(jpg, quality=93, optimize=True, progressive=True)
    proof = out.with_name(out.stem + '-feed.png')
    Image.open(out).convert('RGB').resize(
        (width // 2, height // 2), Image.Resampling.LANCZOS).save(proof)
    print(f'{out.name} ({len(png) // 1024} KiB, {width}x{height}) · {jpg.name} '
          f'({jpg.stat().st_size // 1024} KiB) · {proof.name}')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--background', default=str(HERE / 'background-v1.png'))
    args = parser.parse_args()

    background = pathlib.Path(args.background)
    if not background.is_file():
        print(f'missing background: {background}', file=sys.stderr)
        return 1
    background = press(background)

    images = REPO / 'docs' / 'images'
    render(background, images / 'hero.png', 1600, 900)        # README hero, 16:9
    render(background, images / 'hero-card.png', 1600, 800)   # catalog card, 2:1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
