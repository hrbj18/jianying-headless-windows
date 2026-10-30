"""Local, timestamp-bound overview and detail evidence for source media.

Sampling budgets, protected anchors and numbered contact sheets follow the
haike-workflow-2 material_overview design. Semantic judgments remain explicit
agent submissions; generating images does not mark a video as understood.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import re
import shutil
import subprocess

from analysis_store import digest_file, identity, number, owned_file, read, require, save, verify_source

VERSION = 'jy-media-evidence/v1'


def run(command, timeout=120):
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace',
                            timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    require(result.returncode == 0, 'Local media operation failed: ' + result.stderr[-1200:])
    return result


def binaries():
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    require(ffmpeg and ffprobe, 'FFmpeg and ffprobe are required')
    return ffmpeg, ffprobe


def probe(source):
    import json
    _, ffprobe = binaries()
    data = json.loads(run([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(source)]).stdout)
    videos = [x for x in data['streams'] if x.get('codec_type') == 'video']
    require(len(videos) == 1, 'Material analysis currently requires one video stream')
    video = videos[0]
    duration = float(video.get('duration') or data['format'].get('duration') or 0)
    number(duration, .1, 24 * 3600, 'media duration')
    origin = float(video.get('start_time') or data['format'].get('start_time') or 0)
    return {'duration': duration, 'width': video['width'], 'height': video['height'],
            'pts_origin': origin, 'video_codec': video.get('codec_name'), 'pixel_format': video.get('pix_fmt'),
            'audio': any(x.get('codec_type') == 'audio' for x in data['streams']),
            'audio_codecs': [x.get('codec_name') for x in data['streams'] if x.get('codec_type') == 'audio']}


def duration_policy(duration):
    number(duration, .1, 24 * 3600, 'duration')
    if duration <= 45:
        count, rows, budget = 1, 3, max(18, min(81, math.ceil(duration * 2)))
    elif duration <= 600:
        count, rows, budget = 1, 3, 81
    elif duration <= 3600:
        count, rows, budget = 6, 4, 96
    else:
        count, rows = math.ceil(duration / 600), 4
        budget = count * 16
    return {'chapters': count, 'rows': rows, 'columns': rows, 'frame_budget': budget,
            'whole_video_remote_default': duration <= 3600}


def sampling_plan(duration):
    policy = duration_policy(duration)
    result = []
    for index in range(policy['chapters']):
        start = duration * index / policy['chapters']
        end = duration * (index + 1) / policy['chapters']
        count = policy['frame_budget'] // policy['chapters']
        count += int(index < policy['frame_budget'] % policy['chapters'])
        safe_end = max(start, end - min(.25, (end - start) / 4))
        # Every other sample is a protected coverage anchor. Remaining uniform
        # samples are the information layer; only that layer may be deduplicated.
        times = [start + (safe_end - start) * i / (count - 1) for i in range(count)]
        result.append({'id': 'CHAPTER-' + str(index + 1).zfill(3), 'start': start, 'end': end,
                       'samples': [{'at': t, 'anchor': i % 2 == 0 or i == count - 1} for i, t in enumerate(times)]})
    return policy, result


def _frame(source, at, target, origin, duration):
    ffmpeg, _ = binaries()
    target.parent.mkdir(parents=True, exist_ok=True)
    def capture(position):
        return run([ffmpeg, '-hide_banner', '-y', '-ss', format(position, '.6f'), '-copyts', '-i', str(source),
                    '-map', '0:v:0', '-an', '-frames:v', '1', '-vf', 'showinfo', '-q:v', '3', str(target)])
    try:
        result = capture(at)
    except ValueError:
        # A low-frame-rate file can end after its final presentation timestamp.
        # A bounded local seek may recover that frame; its actual PTS remains
        # checked and labelled below. No fabricated image/time is substituted.
        if duration - at > 1.1:
            raise
        result = capture(max(0, at - 1.05))
    # showinfo may log a second decoded frame even with frames:v=1. The first
    # log belongs to the first encoded JPEG, not the final line in stderr.
    pts = re.findall(r'\bn:\s*0\s+pts:.*?pts_time:([+-]?[0-9]+(?:\.[0-9]+)?)', result.stderr)
    require(pts and target.is_file(), 'Source frame has no verified decoder PTS')
    actual = float(pts[0]) - origin
    require(actual >= -.001 and abs(actual - at) <= 1.1, 'Unexpected source-frame time')
    return {'requested_seconds': at, 'actual_seconds': max(0, actual), 'sha256': digest_file(target)}


def _dhash(image):
    from PIL import Image
    values = list(image.convert('L').resize((9, 8), Image.Resampling.LANCZOS).getdata())
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | int(values[y * 9 + x] > values[y * 9 + x + 1])
    return bits


def sheets(root, frames, rows, columns, prefix):
    from PIL import Image, ImageDraw, ImageOps
    result, cells = [], []
    capacity, cell_size = rows * columns, 512
    for offset in range(0, len(frames), capacity):
        group = frames[offset:offset + capacity]
        sheet_id = prefix + '-S' + str(offset // capacity + 1).zfill(3)
        canvas = Image.new('RGB', (columns * cell_size, rows * cell_size), (22, 25, 32))
        draw = ImageDraw.Draw(canvas)
        for index, frame in enumerate(group):
            row, col = divmod(index, columns)
            x, y = col * cell_size, row * cell_size
            with Image.open(owned_file(root, frame['file'], frame['sha256'])) as im:
                im = ImageOps.contain(im.convert('RGB'), (cell_size - 12, cell_size - 48))
                canvas.paste(im, (x + (cell_size - im.width) // 2, y + 40 + (cell_size - 48 - im.height) // 2))
            cell_id = sheet_id + ':R' + str(row + 1) + 'C' + str(col + 1)
            draw.text((x + 6, y + 10), cell_id + ' / ' + format(frame['actual_seconds'], '.3f') + 's', fill='white')
            cells.append({'id': cell_id, 'frame_id': frame['id'], 'actual_seconds': frame['actual_seconds'],
                          'chapter_id': frame['chapter_id'], 'sheet_id': sheet_id})
        file = 'sheets/' + sheet_id + '.jpg'
        (root / file).parent.mkdir(exist_ok=True)
        canvas.save(root / file, quality=90)
        result.append({'id': sheet_id, 'file': file, 'sha256': digest_file(root / file),
                       'chapter_id': group[0]['chapter_id'], 'rows': rows, 'columns': columns})
    return result, cells


def verify_evidence(root, index):
    require(index.get('schema') == VERSION, 'Unknown evidence schema')
    for row in index['frames'] + index['sheets']:
        owned_file(root, row['file'], row['sha256'])
    ids = {x['id'] for x in index['frames']}
    require(len(ids) == len(index['frames']), 'Duplicate evidence frame IDs')
    require(all(x['frame_id'] in ids for x in index['cells']), 'Unknown evidence cell frame')


def overview(source_record, root):
    root = Path(root)
    source = verify_source(source_record)
    target = root / 'evidence.json'
    if target.exists():
        index = read(target)
        require(index['source_sha256'] == source_record['sha256'], 'Overview source differs')
        verify_evidence(root, index)
        return {**index, 'cache_hit': True}
    media = probe(source)
    policy, chapters = sampling_plan(media['duration'])
    frames, contact_sheets, cells = [], [], []
    for chapter in chapters:
        chapter_frames, seen = [], []
        for sample in chapter.pop('samples'):
            frame_id = 'F' + str(len(frames) + 1).zfill(6)
            file = 'frames/' + frame_id + '.jpg'
            row = {**_frame(source, sample['at'], root / file, media['pts_origin'], media['duration']),
                   'id': frame_id, 'file': file, 'chapter_id': chapter['id'], 'anchor': sample['anchor']}
            from PIL import Image, ImageStat
            with Image.open(root / file) as image:
                fingerprint = _dhash(image)
                color = ImageStat.Stat(image.convert('RGB').resize((32, 32))).mean
            duplicate = next((x for x in seen if (fingerprint ^ x[0]).bit_count() <= 5 and
                              sum(abs(a - b) for a, b in zip(color, x[1])) <= 18), None)
            row['selected'] = sample['anchor'] or duplicate is None
            if row['selected']:
                seen.append((fingerprint, color)); chapter_frames.append(row)
            frames.append(row)
        pages, mappings = sheets(root, chapter_frames, policy['rows'], policy['columns'], chapter['id'])
        contact_sheets += pages; cells += mappings
    verify_source(source_record)
    index = {'schema': VERSION, 'source_sha256': source_record['sha256'], 'media': media, 'policy': policy,
             'chapters': chapters, 'frames': frames, 'sheets': contact_sheets, 'cells': cells, 'cache_hit': False}
    save(target, index)
    return index


def detail(source_record, root, media, candidate_id, start, end, fps=2):
    source = verify_source(source_record)
    number(start, 0, media['duration'], 'detail start')
    number(end, start + .1, media['duration'], 'detail end')
    number(fps, .5, 5, 'detail fps')
    key = identity({'schema': VERSION, 'source': source_record['sha256'], 'candidate': candidate_id,
                    'start': start, 'end': end, 'fps': fps, 'max_frames': 24})
    folder = Path(root) / 'details' / key[:20]
    path = folder / 'evidence.json'
    if path.exists():
        result = read(path); verify_evidence(folder, result)
        return {**result, 'cache_hit': True, 'path': str(path)}
    folder.mkdir(parents=True, exist_ok=True)
    count = min(24, max(2, math.ceil((end - start) * fps)))
    safe_end = max(start, end - min(.05, (end - start) / 4))
    frames = []
    for i in range(count):
        at = start + (safe_end - start) * i / (count - 1)
        file = 'frames/D' + str(i + 1).zfill(3) + '.jpg'
        frames.append({**_frame(source, at, folder / file, media['pts_origin'], media['duration']), 'id': 'D' + str(i + 1).zfill(3),
                       'file': file, 'chapter_id': candidate_id, 'anchor': True, 'selected': True})
    pages, cells = sheets(folder, frames, 3, 3, candidate_id)
    result = {'schema': VERSION, 'source_sha256': source_record['sha256'], 'candidate_id': candidate_id,
              'start': start, 'end': end, 'frames': frames, 'sheets': pages, 'cells': cells,
              'requested_fps': fps, 'sample_policy': 'even samples, at most 24 frames; not continuous playback',
              'cache_hit': False}
    save(path, result)
    return {**result, 'path': str(path)}


def extract_audio(source, target, start, duration):
    ffmpeg, _ = binaries()
    target = Path(target)
    if target.exists():
        require(target.stat().st_size > 44, 'Cached audio is empty')
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_name(target.stem + '.pending.wav')
    run([ffmpeg, '-v', 'error', '-y', '-ss', str(start), '-i', str(source), '-t', str(duration),
         '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(pending)],
        timeout=max(120, duration * 2))
    require(pending.stat().st_size > 44, 'Source has no usable audio')
    os.replace(pending, target)
    return target
