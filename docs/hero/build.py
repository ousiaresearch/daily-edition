#!/usr/bin/env python3.14
"""Compose the Daily Edition hero: a generated print still life plus vector typography.

Route (a) of the branded-card procedure: the raster carries the argument with no legible text, and
every word is vector type laid over it with the print's own defect echoed (a second plate landing a
hair off) so the type reads as printed rather than pasted.

    python3.14 docs/hero/build.py [--background PATH] [--out PATH]

Sources kept beside the output: `prompt.txt` (the generation brief), this script, and `hero.svg`
(written on every run).
"""

import argparse
import base64
import pathlib
import re
import sys

import resvg_py
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent

W, H = 1600, 900
ZOOM = 1.08
CREAM = '#F0E7D4'
BODY = '#E2D6BF'
MUTED = '#BCAC94'
VERMILION = '#C4553C'
SERIF = "'Iowan Old Style', 'Palatino Linotype', Palatino, Baskerville, 'Times New Roman', serif"
SANS = "'Helvetica Neue', Helvetica, Arial, sans-serif"

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
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def svg(background: pathlib.Path) -> str:
    label, name, phrase = COPY['label'], COPY['name'], COPY['phrase']
    question, footer = COPY['question'], COPY['footer']
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
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

  <image href="{data_uri(background)}" x="{-(W * (ZOOM - 1) / 2) - 18:.1f}" y="{-(H * (ZOOM - 1) / 2):.1f}"
         width="{W * ZOOM:.1f}" height="{H * ZOOM:.1f}" preserveAspectRatio="xMidYMid slice"/>
  <rect x="0" y="0" width="{W}" height="{H}" fill="url(#scrim)"/>
  <rect x="0" y="0" width="{W}" height="{H}" filter="url(#grain)" opacity="0.55"/>

  <g font-family="{SANS}">
    <text x="88" y="196" fill="#D8664A" font-size="19" letter-spacing="6.6"
          font-weight="500">{esc(label)}</text>
    <rect x="88" y="216" width="224" height="1" fill="#8A7355" opacity="0.8"/>
  </g>

  <!-- the second plate: the same words in vermilion, a hair off, as a second print pass -->
  <g font-family="{SERIF}" font-size="104" fill="{VERMILION}" opacity="0.22" filter="url(#soften)">
    <text x="91" y="333">{esc(name[0])}</text>
    <text x="91" y="448">{esc(name[1])}</text>
  </g>
  <g font-family="{SERIF}" font-size="104" fill="{CREAM}" letter-spacing="-1">
    <text x="88" y="330">{esc(name[0])}</text>
    <text x="88" y="445">{esc(name[1])}</text>
  </g>

  <rect x="88" y="492" width="520" height="1" fill="#5A4A36" opacity="0.9"/>

  <g font-family="{SERIF}" font-size="33" font-style="italic" fill="{BODY}">
    <text x="88" y="552">{esc(phrase)}</text>
  </g>
  <g font-family="{SANS}" font-size="23" fill="#CBBEA6" letter-spacing="0.4">
    <text x="88" y="598">{esc(question)}</text>
  </g>

  <g font-family="{SANS}" fill="#C4B49B" letter-spacing="2.8">
    <text x="88" y="818" font-size="18">{esc(footer[0])}</text>
    <text x="88" y="852" letter-spacing="0.5" font-size="21" fill="#D2C2A8">{esc(footer[1])}</text>
  </g>

  <!-- one grain field over everything, so the vector type shares the print's surface -->
  <rect x="0" y="0" width="{W}" height="{H}" filter="url(#grain)" opacity="0.16"/>
</svg>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--background', default=str(HERE / 'background-v1.png'))
    parser.add_argument('--out', default=str(REPO / 'docs' / 'images' / 'hero.png'))
    args = parser.parse_args()

    background = pathlib.Path(args.background)
    if not background.is_file():
        print(f'missing background: {background}', file=sys.stderr)
        return 1
    background = press(background)

    source = svg(background).encode('utf-8')
    (HERE / 'hero.svg').write_bytes(source)
    png = bytes(resvg_py.svg_to_bytes(svg_string=source.decode('utf-8'), width=W, height=H))
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)

    # a lighter copy for the README; the PNG stays the master
    jpg = out.with_suffix('.jpg')
    Image.open(out).convert('RGB').save(jpg, quality=93, optimize=True, progressive=True)

    # feed-scale proof: what the card actually looks like in a timeline
    proof = out.with_name(out.stem + '-feed.png')
    Image.open(out).convert('RGB').resize((800, 450), Image.Resampling.LANCZOS).save(proof)
    print(f'{out} ({len(png) // 1024} KiB, {W}x{H})')
    print(f'{jpg} ({jpg.stat().st_size // 1024} KiB)')
    print(f'{proof} (800x450 feed proof)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
