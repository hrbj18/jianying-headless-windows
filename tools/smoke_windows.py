#!/usr/bin/env python3
"""Run the normal CLI against new synthetic media and an isolated disk draft."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / 'jianying.py'
job = None
report = {'status': 'running', 'entrypoint': str(ENTRY), 'steps': [],
          'synthetic_input_only': True, 'experimental_runtime_overrides': False}


def command(label, *arguments, timeout=120):
    result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(ENTRY), *map(str, arguments)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    if job:
        (job / (label + '.stdout.json')).write_text(result.stdout, encoding='utf-8')
        (job / (label + '.stderr.log')).write_text(result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(label + ' failed: ' + result.stderr[-3000:])
    value = json.loads(result.stdout)
    report['steps'].append({'name': label, 'exit_code': result.returncode,
                            'status': value.get('status'), 'command': list(map(str, arguments))})
    print(label + ': passed', flush=True)
    return value


try:
    runtime = command('doctor', 'doctor')
    assert runtime['status'] == 'ready' and runtime['app_build'] == '11.4.7.14462'
    report['runtime'] = runtime
    workspace_info = command('workspace', 'workspace', '--name', 'normal-cli')
    job = Path(workspace_info['job'])
    source = job / 'source.mp4'
    ffmpeg = runtime['ffmpeg']
    subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-n', '-f', 'lavfi', '-i',
        'testsrc2=size=640x360:rate=30:duration=4', '-f', 'lavfi', '-i',
        'sine=frequency=440:sample_rate=44100:duration=4', '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(source)], check=True, timeout=60)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    plan = {'schema': 'jy14-headless-plan/v1', 'name': job.name,
        'canvas': {'width': 640, 'height': 360, 'fps': 30}, 'tracks': [
            {'type': 'video', 'segments': [{'source': str(source), 'start_us': 0,
                'duration_us': 3000000, 'source_start_us': 500000,
                'source_duration_us': 3000000, 'scale': .8, 'volume': .4}]},
            {'type': 'text', 'segments': [{'text': 'Normal 11.4.7 build',
                'start_us': 0, 'duration_us': 3000000, 'size': 8}]}]}
    plan_file = job / 'plan.json'
    plan_file.write_text(json.dumps(plan), encoding='utf-8')
    command('build', 'build', '--plan', plan_file, '--out', job / 'build')
    command('verify-build', 'verify-build', '--build', job / 'build')
    build = json.loads((job / 'build/build.json').read_text(encoding='utf-8'))
    assert build['runtime_profile'] == 'jy14-headless-windows-11.4.7.14462'
    built_export = command('export-build', 'export', '--build', job / 'build',
        '--out', job / 'render-build', '--timeout', '60')
    assert built_export['status'] == 'encoded-and-decoded'

    workspace = Path(workspace_info['blueprint'])
    draft_root = Path(workspace_info['draft_root'])
    draft_name = job.name + '-edited'
    ref = 'local://' + draft_name
    draft = draft_root / draft_name
    command('lyra-init', 'lyra', 'init', '--workspace', workspace, '--timeout', '30')
    command('lyra-create', 'lyra', 'create', '--draft-root', draft_root, '--ref', ref, '--timeout', '30')
    command('lyra-sync-empty', 'lyra', 'sync', '--workspace', workspace,
        '--draft-root', draft_root, '--ref', ref, '--timeout', '30')
    command('lyra-import', 'lyra', 'resource-import', '--workspace', workspace,
        '--draft-root', draft_root, '--path', source, '--title', 'Normal CLI synthetic source', '--timeout', '30')
    resources = json.loads((workspace / 'resource_map.json').read_text(encoding='utf-8'))
    video = next(item for item in resources if item.get('type') == 'video'
        and Path(item.get('path', '')).resolve() == source.resolve())
    selection = workspace / 'edit.selection'
    selection.write_text('draft.select("main").appendXml(`<video id="v_normal" ref="' +
        video['asset_id'] + '" volume="100"><time material_start="0" duration="4000" speed="1"/></video>`);\n'
        'draft.select("multi").appendXml(`<text id="t_normal"><time start="0" duration="3000"/>'
        '<content><sub text="Before normal edit" size="12"/></content></text>`);\ndraft.apply();\n', encoding='utf-8')
    command('lyra-append', 'lyra', 'apply', '--workspace', workspace, '--draft-dir', draft,
        '--ref', ref, '--selection-file', selection, '--timeout', '30')
    command('lyra-sync-baseline', 'lyra', 'sync', '--workspace', workspace,
        '--draft-root', draft_root, '--ref', ref, '--timeout', '30')
    before = ET.fromstring((workspace / 'current_draft.xml').read_text(encoding='utf-8'))
    video_id = before.find('./main/video').attrib['id']
    text_id = before.find('./multi/text').attrib['id']
    assert all(value.replace('_', '').replace('-', '').isalnum() for value in (video_id, text_id))
    selection.write_text(f'draft.select("#{video_id} time").attr("duration", "3000");\n'
        f'draft.select("#{video_id}").attr("volume", "25");\n'
        f'draft.select("#{text_id} content sub").attr("text", "Normal CLI 11.4.7 passed");\n'
        'draft.apply();\n', encoding='utf-8')
    command('lyra-edit', 'lyra', 'apply', '--workspace', workspace, '--draft-dir', draft,
        '--ref', ref, '--selection-file', selection, '--timeout', '30')
    command('lyra-readback', 'lyra', 'sync', '--workspace', workspace,
        '--draft-root', draft_root, '--ref', ref, '--current-only', '--timeout', '30')
    after = ET.fromstring((workspace / 'current_draft.xml').read_text(encoding='utf-8'))
    assert after.find('./main/video/time').attrib['duration'] == '3000'
    assert after.find('./main/video').attrib['volume'] == '25'
    assert after.find('./multi/text/content/sub').attrib['text'] == 'Normal CLI 11.4.7 passed'
    edited_export = command('export-draft', 'export-draft', '--draft-dir', draft,
        '--out', job / 'render-edited', '--timeout', '60')
    assert edited_export['status'] == 'encoded-and-decoded'
    for name in ('render-build', 'render-edited'):
        subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-ss', '1', '-i',
            str(job / name / 'render.mp4'), '-frames:v', '1', str(job / name / 'frame.png')], check=True, timeout=30)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    report.update(status='normal-entry-end-to-end-passed', job=str(job),
        build_profile=build['runtime_profile'], source_unchanged=True,
        build_output=str(job / 'render-build/render.mp4'),
        edited_output=str(job / 'render-edited/render.mp4'),
        editing_readback={'duration_ms': 3000, 'volume_percent': 25, 'text': 'Normal CLI 11.4.7 passed'})
except Exception as error:
    report.update(status='failed', error=str(error), traceback=traceback.format_exc())
finally:
    if job:
        report['job'] = str(job)
        (job / 'smoke-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
sys.exit(0 if report['status'] == 'normal-entry-end-to-end-passed' else 1)
