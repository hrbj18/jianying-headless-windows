"""Create original local sound punctuation and transparent comic shapes for native editing.

This generates source assets only. It never mixes the source dialogue or renders video.
"""
import argparse
import json
from pathlib import Path
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def create(out, seconds=60):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sr = 48000
    rng = np.random.default_rng(1977)
    records = []

    def write(name, samples):
        samples = np.clip(samples, -.95, .95)
        stereo = np.column_stack([samples, samples * .985])
        file = out / (name + '.wav')
        with wave.open(str(file), 'wb') as stream:
            stream.setnchannels(2); stream.setsampwidth(2); stream.setframerate(sr)
            stream.writeframes((stereo * 32767).astype('<i2').tobytes())
        records.append({'file': str(file), 'seconds': len(samples) / sr,
                        'peak': round(float(abs(samples).max()), 6),
                        'rms': round(float(np.sqrt(np.mean(samples ** 2))), 6)})

    t = np.arange(sr) / sr
    write('comic-fall', .45 * np.sin(2 * np.pi * (630 * t - 270 * t*t)) * np.exp(-8*t)
          + .22 * rng.normal(size=sr) * np.exp(-40*t))
    write('soft-thud', .53 * np.sin(2*np.pi * (94*t - 31*t*t))*np.exp(-22*t)
          + .09 * rng.normal(size=sr)*np.exp(-47*t))
    write('pop', .5*np.sin(2*np.pi*(780*t - 410*t*t))*np.exp(-32*t))
    write('rewind', .23*np.sin(2*np.pi*(100*t + 920*t*t))*np.exp(-10*t)
          + .08*rng.normal(size=sr)*np.exp(-15*t))
    bell = sum(np.sin(2*np.pi*f*t) * a for f,a in [(1046.5,.28),(1569.75,.10),(2093,.04)])
    write('success', bell * np.minimum(t/.012,1) * np.exp(-5.8*t))
    sparkle = np.zeros(sr)
    for delay, freq in [(0,659.25),(.12,830.61),(.24,987.77)]:
        local=t-delay
        sparkle += np.where(local >= 0,.23*np.sin(2*np.pi*freq*local)*np.exp(-9*np.maximum(local,0)),0)
    write('warm-chime', sparkle)

    # Light pizzicato accompaniment, with real rests and an unobtrusive bass.
    length = round(seconds*sr)
    score = np.zeros(length); beat = 60/112
    chords = [(60,64,67),(57,60,64),(53,57,60),(55,59,62)]
    melody = [0,2,1,None,2,None,1,None, 0,None,1,2,None,1,None,None]
    for step in range(int(seconds/(beat/2))+1):
        start=round(step*beat/2*sr)
        if start>=length: break
        chord=chords[(step//16)%len(chords)]
        if melody[step%16] is not None:
            midi=chord[melody[step%16]]+12
            local=np.arange(round(.34*sr))/sr; freq=440*2**((midi-69)/12)
            tone=(np.sin(2*np.pi*freq*local)+.22*np.sin(4*np.pi*freq*local))*np.exp(-15*local)
            tone*=np.minimum(local/.006,1)*.14
            n=min(len(tone),length-start);score[start:start+n]+=tone[:n]
        if step%4==0:
            local=np.arange(round(.28*sr))/sr;freq=440*2**((chord[0]-12-69)/12)
            bass=.10*np.sin(2*np.pi*freq*local)*np.exp(-12*local)
            n=min(len(bass),length-start);score[start:start+n]+=bass[:n]
    envelope=np.minimum(np.arange(length)/sr/1.2,1)*np.minimum((length-1-np.arange(length))/sr/1.6,1)
    write('playful-pizzicato', score*envelope)

    # Full-canvas transparent shapes are independently editable native overlays.
    def canvas():return Image.new('RGBA',(912,1920),(0,0,0,0))
    sweat=canvas();d=ImageDraw.Draw(sweat)
    for x,y,size in [(705,960,46),(754,1003,25),(664,1018,22)]:
        d.polygon([(x,y-size),(x-size//2,y+size//3),(x+size//2,y+size//3)],fill='#58CFFF',outline='#173C70',width=5)
        d.ellipse((x-size//2,y,x+size//2,y+size),fill='#58CFFF',outline='#173C70',width=5)
        d.ellipse((x-size//4,y+size//5,x,y+size//2),fill='#E8FAFF')
    sweat.save(out/'sweat.png')
    question=canvas();d=ImageDraw.Draw(question)
    font=ImageFont.truetype('C:/Windows/Fonts/Dengb.ttf',102)
    for x,y,s in [(650,930,1),(735,888,1),(760,1020,1)]:
        d.text((x,y),'?',font=font,fill='#FFDE46',stroke_width=7,stroke_fill='#38200D')
    question.save(out/'questions.png')
    ring=canvas();d=ImageDraw.Draw(ring)
    # The circle is centered on the face PIP position used by the example plan.
    d.ellipse((54,378,294,618),outline='#FFF8DF',width=15)
    d.ellipse((47,371,301,625),outline='#1DB7DF',width=6)
    ring.save(out/'reaction-ring.png')
    star=canvas();d=ImageDraw.Draw(star)
    cx,cy=466,1390;points=[]
    for i in range(20):
        radius=170 if i%2==0 else 92;angle=i*np.pi/10
        points.append((cx+radius*np.cos(angle),cy+radius*np.sin(angle)))
    d.polygon(points,fill='#FFE97488',outline='#FFF7CC',width=9)
    star.save(out/'impact.png')
    manifest={'provenance':'Original deterministic procedural synthesis and graphic shapes; no reference soundtrack copied.',
              'audio':records,'graphics':[str(p) for p in sorted(out.glob('*.png'))]}
    (out/'assets.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path);p.add_argument('--seconds',type=float,default=60)
    a=p.parse_args()
    if not a.out.is_absolute() or not 1 <= a.seconds <= 600:p.error('Use an absolute output and 1..600 seconds')
    print(json.dumps(create(a.out,a.seconds),ensure_ascii=False,indent=2))
