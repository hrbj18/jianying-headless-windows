"""Make transparent editable comic bubble backplates; no text or video render.

Example from another script:
    render_bubble(out, 'reply-01', 'dialogue', rect=(80, 100, 560, 330),
                  tail_tip=(510, 410), accent='pink')

Coordinates are pixels in the full 912 x 1920 source canvas. Rect denotes the
bubble body, not its tail. SVG paths are the source of the Pillow geometry;
the same commands are sampled for the PNG. Body, shadow and accents remain
separate named SVG elements. This module does not rasterize text.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from html import escape
import math
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont


CANVAS = (912, 1920)
INK = '#292535'
CREAM = '#FFF8E9'
ACCENTS = {'pink': '#F2ABC4', 'blue': '#A2DDEB', 'yellow': '#F2D370'}
DEFAULT_ACCENTS = {'dialogue': 'pink', 'concern': 'blue', 'praise': 'yellow'}
VARIANTS = tuple(DEFAULT_ACCENTS)


def number(value):
    return format(float(value), '.3f').rstrip('0').rstrip('.') or '0'


def color(value):
    value = ACCENTS.get(value, value)
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('accent must be pink/blue/yellow or #RRGGBB')
    return value.upper()


def rgba(value, alpha=255):
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5)) + (alpha,)


@dataclass
class PathShape:
    commands: list = field(default_factory=list)
    points: list = field(default_factory=list)

    def move(self, x, y):
        self.commands.append(('M', x, y))
        self.points.append((x, y))

    def line(self, x, y):
        self.commands.append(('L', x, y))
        self.points.append((x, y))

    def quad(self, cx, cy, x, y):
        self.commands.append(('Q', cx, cy, x, y))
        ax, ay = self.points[-1]
        for i in range(1, 17):
            t = i / 16
            self.points.append(((1-t)**2*ax + 2*(1-t)*t*cx + t*t*x,
                                (1-t)**2*ay + 2*(1-t)*t*cy + t*t*y))

    def close(self):
        self.commands.append(('Z',))
        self.points.append(self.points[0])

    @property
    def d(self):
        return ' '.join(c[0] + (' ' + ' '.join(number(v) for v in c[1:]) if len(c) > 1 else '')
                        for c in self.commands)


def tail_side(rect, tip):
    x1, y1, x2, y2 = rect
    tx, ty = tip
    if x1 <= tx <= x2 and y1 <= ty <= y2:
        raise ValueError('tail_tip must be outside the bubble body')
    distances = {'top': (y1-ty)/(y2-y1), 'bottom': (ty-y2)/(y2-y1),
                 'left': (x1-tx)/(x2-x1), 'right': (tx-x2)/(x2-x1)}
    return max(distances, key=distances.get)


def rounded_body(rect, tip, concern=False):
    x1, y1, x2, y2 = rect
    width, height = x2-x1, y2-y1
    radius = min(46 if concern else 37, height*.24, width*.14)
    side = tail_side(rect, tip)
    half = min(33, width*.075, height*.18)
    path = PathShape()
    path.move(x1+radius, y1)

    def edge(name, a, b):
        if name != side:
            path.line(*b)
            return
        vertical = a[0] == b[0]
        length = abs((b[1]-a[1]) if vertical else (b[0]-a[0]))
        h = min(half, length*.24)
        projected = tip[1] if vertical else tip[0]
        lo = min(a[1], b[1]) if vertical else min(a[0], b[0])
        hi = max(a[1], b[1]) if vertical else max(a[0], b[0])
        anchor = max(lo+h+3, min(hi-h-3, projected))
        direction = 1 if (b[1] > a[1] if vertical else b[0] > a[0]) else -1
        first, last = anchor-direction*h, anchor+direction*h
        if vertical:
            path.line(a[0], first)
            path.line(*tip)
            path.line(a[0], last)
        else:
            path.line(first, a[1])
            path.line(*tip)
            path.line(last, a[1])
        path.line(*b)

    edge('top', (x1+radius,y1), (x2-radius,y1))
    path.quad(x2,y1,x2,y1+radius)
    edge('right', (x2,y1+radius), (x2,y2-radius))
    path.quad(x2,y2,x2-radius,y2)
    edge('bottom', (x2-radius,y2), (x1+radius,y2))
    path.quad(x1,y2,x1,y2-radius)
    edge('left', (x1,y2-radius), (x1,y1+radius))
    path.quad(x1,y1,x1+radius,y1)
    path.close()
    return path


def praise_body(rect, tip):
    """A restrained 12-ray burst with a single integrated pointer."""
    x1,y1,x2,y2 = rect
    cx,cy = (x1+x2)/2,(y1+y2)/2
    rx,ry = (x2-x1)/2,(y2-y1)/2
    points = []
    # Clockwise perimeter, with small unequal rays rather than a loud star.
    for i in range(24):
        angle = -math.pi/2 + i*math.tau/24
        factor = 1 if i % 2 == 0 else .865
        points.append((cx+rx*factor*math.cos(angle),cy+ry*factor*math.sin(angle)))
    # Replace one nearby boundary vertex with the tail; the two neighbours
    # remain a clear base, so no dark seam crosses the cream body.
    tx,ty = tip
    direction = ((tx-cx)/rx,(ty-cy)/ry)
    index = max(range(len(points)),key=lambda i: (points[i][0]-cx)/rx*direction[0]
                                                + (points[i][1]-cy)/ry*direction[1])
    points[index] = tip
    path = PathShape()
    path.move(*points[0])
    for point in points[1:]:
        path.line(*point)
    path.close()
    return path


def build_geometry(variant, rect, tail_tip):
    if variant not in VARIANTS:
        raise ValueError('variant must be dialogue, concern or praise')
    rect = tuple(map(float, rect)); tail_tip = tuple(map(float, tail_tip))
    if len(rect) != 4 or len(tail_tip) != 2 or not all(math.isfinite(v) for v in (*rect,*tail_tip)):
        raise ValueError('rect/tail_tip require finite coordinates')
    x1,y1,x2,y2 = rect
    if x2-x1 < 180 or y2-y1 < 100:
        raise ValueError('body requires width >= 180 and height >= 100 pixels')
    for x,y in ((x1,y1),(x2,y2),tail_tip):
        if not (12 <= x <= CANVAS[0]-20 and 12 <= y <= CANVAS[1]-22):
            raise ValueError('body/tail must keep a safe 12-22 pixel canvas margin')
    tail_side(rect,tail_tip)
    shape = praise_body(rect,tail_tip) if variant == 'praise' else rounded_body(rect,tail_tip,variant=='concern')
    return shape,rect,tail_tip


def render_bubble(out_dir, name, variant='dialogue', *, rect=(80,100,560,330),
                  tail_tip=(505,410), accent=None, supersample=3):
    """Return PNG/SVG paths for a precise full-frame text-free backplate.

    Accent is a palette name or #RRGGBB. The tail side is chosen from its tip.
    `rect` and `tail_tip` are source-canvas coordinates, never normalized.
    """
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',name):
        raise ValueError('name must be a simple ASCII asset basename')
    if supersample not in (2,3,4):
        raise ValueError('supersample must be 2, 3 or 4')
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    shape,rect,tail_tip=build_geometry(variant,rect,tail_tip)
    accent=color(accent or DEFAULT_ACCENTS[variant])
    x1,y1,x2,y2=rect
    sw=7.5 if variant=='praise' else 7
    decoration=[]
    # Small accent marks leave the central area free for editable native text.
    if variant=='praise':
        marks=[(x1+(x2-x1)*.28,y1+(y2-y1)*.28,4.5),
               (x1+(x2-x1)*.72,y1+(y2-y1)*.72,3.5)]
        stripe=None
    else:
        marks=[(x1+36,y1+31,4),(x1+51,y1+31,3)]
        stripe=((x2-66,y2-24),(x2-35,y2-24))
    for i,(x,y,radius) in enumerate(marks):
        decoration.append(f'    <circle id="accent-dot-{i+1}" cx="{number(x)}" cy="{number(y)}" r="{number(radius)}" fill="{accent}"/>')
    if stripe:
        decoration.append(f'    <path id="accent-stroke" d="M {number(stripe[0][0])} {number(stripe[0][1])} L {number(stripe[1][0])} {number(stripe[1][1])}" stroke="{accent}" stroke-width="6" stroke-linecap="round" fill="none"/>')
    svg='\n'.join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS[0]}" height="{CANVAS[1]}" viewBox="0 0 {CANVAS[0]} {CANVAS[1]}">',
        f'  <title>{escape(name)} comic bubble backplate</title>',
        '  <desc>Transparent full canvas. No text is embedded. Coordinates are pixels. Edit the named paths and accent group.</desc>',
        f'  <!-- variant={variant}; body-rect={",".join(map(number,rect))}; tail-tip={",".join(map(number,tail_tip))} -->',
        f'  <path id="bubble-shadow" d="{shape.d}" transform="translate(7 10)" fill="{INK}" fill-opacity="0.13"/>',
        f'  <path id="bubble-body-and-tail" d="{shape.d}" fill="{CREAM}" stroke="{INK}" stroke-width="{number(sw)}" stroke-linejoin="round" stroke-linecap="round"/>',
        '  <g id="accent-marks">',*decoration,'  </g>','</svg>',''])
    svg_path=out_dir/(name+'.svg');svg_path.write_text(svg,encoding='utf-8',newline='\n')
    scale=supersample
    image=Image.new('RGBA',(CANVAS[0]*scale,CANVAS[1]*scale),(0,0,0,0))
    draw=ImageDraw.Draw(image)
    points=[(round(x*scale),round(y*scale)) for x,y in shape.points]
    draw.polygon([(x+7*scale,y+10*scale) for x,y in points],fill=rgba(INK,33))
    draw.polygon(points,fill=rgba(CREAM))
    draw.line(points,fill=rgba(INK),width=round(sw*scale),joint='curve')
    for x,y,radius in marks:
        draw.ellipse(((x-radius)*scale,(y-radius)*scale,(x+radius)*scale,(y+radius)*scale),fill=rgba(accent))
    if stripe:
        a,b=stripe
        draw.line((a[0]*scale,a[1]*scale,b[0]*scale,b[1]*scale),fill=rgba(accent),width=6*scale)
        for x,y in stripe:
            draw.ellipse(((x-3)*scale,(y-3)*scale,(x+3)*scale,(y+3)*scale),fill=rgba(accent))
    image=image.resize(CANVAS,Image.Resampling.LANCZOS)
    png_path=out_dir/(name+'.png');image.save(png_path)
    return {'png':str(png_path),'svg':str(svg_path),'variant':variant,'rect':rect,'tail_tip':tail_tip,'accent':accent}


def make_contactsheet(results, out_file):
    """Cropped detail panels over a checkerboard, not a video template."""
    panel_width,panel_height=630,460
    sheet=Image.new('RGB',(panel_width*len(results),panel_height),'#F5F2EF')
    draw=ImageDraw.Draw(sheet)
    try:
        font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',21)
    except OSError:
        font=ImageFont.load_default()
    for i,result in enumerate(results):
        left=i*panel_width
        for y in range(52,panel_height,22):
            for x in range(left+8,left+panel_width-8,22):
                draw.rectangle((x,y,min(x+21,left+panel_width-8),min(y+21,panel_height-8)),fill='#E6E4E3' if ((x-left)//22+y//22)%2 else '#FAF9F6')
        draw.text((left+20,14),result['variant'].upper()+' / transparent backplate',fill=INK,font=font)
        source=Image.open(result['png']).convert('RGBA')
        bounds=source.getchannel('A').getbbox()
        if bounds:
            x1,y1,x2,y2=bounds
            source=source.crop((max(0,x1-24),max(0,y1-24),
                                min(CANVAS[0],x2+24),min(CANVAS[1],y2+24)))
        source.thumbnail((panel_width-30,panel_height-70),Image.Resampling.LANCZOS)
        sheet.paste(source,(left+(panel_width-source.width)//2,
                            58+(panel_height-70-source.height)//2),source)
    sheet.save(out_file)
    return str(out_file)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True,help='Absolute private output directory; never defaults to the source tree')
    parser.add_argument('--variant',choices=(*VARIANTS,'all'),default='all')
    parser.add_argument('--name',default='comic')
    parser.add_argument('--rect',type=float,nargs=4,default=(80,100,560,330),metavar=('X1','Y1','X2','Y2'))
    parser.add_argument('--tail',type=float,nargs=2,default=(505,410),metavar=('X','Y'))
    parser.add_argument('--accent',default=None)
    args=parser.parse_args()
    if not args.out.is_absolute():
        parser.error('--out must be an absolute output directory')
    variants=VARIANTS if args.variant=='all' else (args.variant,)
    results=[render_bubble(args.out,args.name+'-'+variant,variant,rect=args.rect,tail_tip=args.tail,accent=args.accent) for variant in variants]
    for result in results:
        print(result['png']);print(result['svg'])
    if len(results)>1:
        print(make_contactsheet(results,args.out/(args.name+'-contactsheet.png')))


if __name__=='__main__':
    main()
