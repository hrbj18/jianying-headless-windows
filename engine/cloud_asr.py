"""Bailian file ASR, adapted from haike-workflow-2's durable ASR contract.

Only credential-file references are configured here. Upload authorizations and
accepted task IDs stay in private job records, never in CLI summaries or source.
There is no automatic paid submission retry or provider substitution.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
import uuid

from analysis_store import digest_file, identity, lock, number, read, require, save
from local_config import load_config

MODEL = 'qwen-audio-3.1-asr-flash-filetrans'


class ASRError(ValueError):
    def __init__(self, message, *, accepted=False, task_id=None, unknown=False):
        super().__init__(message)
        self.accepted, self.task_id, self.unknown = bool(accepted or task_id), task_id, unknown


def configuration(settings=None):
    settings = (load_config().get('analysis', {}) if settings is None else settings)
    require(isinstance(settings, dict) and set(settings) <= {'credential_files', 'asr_model', 'chunk_seconds'},
            'Analysis settings accept credential_files, asr_model and chunk_seconds only')
    paths = settings.get('credential_files', [])
    require(isinstance(paths, list) and all(isinstance(p, str) and Path(p).is_absolute() for p in paths),
            'Analysis credential_files must contain absolute paths')
    names = ('DASHSCOPE_API_KEY', 'DASHSCOPE_WORKSPACE_ID')
    values = {key: os.environ[key] for key in names if os.environ.get(key)}
    if paths:
        from dotenv import dotenv_values
        for name in paths:
            path = Path(name)
            require(path.is_file() and not path.is_symlink(), 'Configured ASR credential file is unavailable')
            for key, value in dotenv_values(path, interpolate=False, encoding='utf-8-sig').items():
                if key in names and key not in values and value:
                    values[key] = value
    key = values.get('DASHSCOPE_API_KEY', '').strip()
    require(key and '\n' not in key and '\r' not in key, '阿里云 ASR Key 未配置')
    workspace = values.get('DASHSCOPE_WORKSPACE_ID', '').strip()
    require(not workspace or re.fullmatch(r'[A-Za-z0-9-]{1,80}', workspace), 'Invalid ASR workspace')
    host = workspace + '.cn-beijing.maas.aliyuncs.com' if workspace else 'dashscope.aliyuncs.com'
    model = settings.get('asr_model', MODEL)
    require(model == MODEL, 'Only the reviewed Bailian file ASR model is enabled')
    return {'key': key, 'base': 'https://' + host + '/api/v1', 'model': model,
            'scope': identity({'credential': key, 'workspace': workspace}),
            'chunk_seconds': number(settings.get('chunk_seconds', 600), 10, 600, 'chunk_seconds')}


def public_config(config):
    return {'provider': 'bailian', 'model': config['model'], 'endpoint': config['base'],
            'credential_scope': config['scope'], 'audio_format': 'mono16k-wav-v1',
            'chunk_seconds': config['chunk_seconds'], 'credential_available': True}


def safe_error(value, config):
    message = str(value).replace(config.get('key', ''), '[redacted]') if config.get('key') else str(value)
    message = re.sub(r'https?://[^\s"\']+', '[cloud URL redacted]', message)
    return message[:600]


def _url(url):
    parts = urlsplit(url)
    require(parts.scheme == 'https' and parts.hostname and parts.hostname.endswith('.aliyuncs.com')
            and not parts.username and not parts.password and parts.port in {None, 443},
            'ASR returned an unreviewed remote host')
    return url


def _json(response, config):
    try:
        value = response.json()
    except ValueError:
        raise ASRError('阿里云返回无效 JSON；保留任务记录后核对') from None
    if not isinstance(value, dict) or response.status_code >= 400 or value.get('code'):
        code = value.get('code') if isinstance(value, dict) else ''
        raise ASRError(safe_error('阿里云请求失败：HTTP ' + str(response.status_code) + ' ' + str(code), config))
    return value


def normalize(payload, duration):
    """Keep each sentence's real words; never invent absent ASR timestamps."""
    segments = []
    require(isinstance(payload, dict) and isinstance(payload.get('transcripts'), list),
            'ASR result has no transcripts')
    for transcript in payload['transcripts']:
        for sentence in transcript.get('sentences', []):
            start_ms = number(sentence.get('begin_time'), 0, (duration + 1) * 1000, 'ASR begin_time')
            end_ms = number(sentence.get('end_time'), start_ms, (duration + 1) * 1000, 'ASR end_time')
            start, end = start_ms / 1000, end_ms / 1000
            require(start < end and isinstance(sentence.get('text'), str), 'Invalid ASR sentence')
            words = []
            for word in sentence.get('words') or []:
                # Compare provider milliseconds directly. A seconds round trip
                # can turn 32260 into 32259.999999999996 and reject real data.
                a_ms = number(word.get('begin_time'), start_ms, end_ms, 'word begin_time')
                b_ms = number(word.get('end_time'), a_ms, end_ms, 'word end_time')
                a, b = a_ms / 1000, b_ms / 1000
                require(isinstance(word.get('text'), str), 'Invalid ASR word')
                words.append({'start': a, 'end': b, 'text': word['text']})
            segments.append({'start': start, 'end': end, 'text': sentence['text'], 'words': words,
                             **({'speaker_id': sentence['speaker_id']} if 'speaker_id' in sentence else {})})
    return segments


def transcribe(audio, folder, config, duration, *, http=None, timeout=900, poll_seconds=3):
    """Resume one exact operation; uncertain POST outcomes never submit again."""
    audio, folder = Path(audio), Path(folder)
    frozen = {'audio_sha256': digest_file(audio), 'runtime': public_config(config)}
    frozen['runtime'].pop('chunk_seconds')
    require(audio.is_file() and audio.stat().st_size <= 24 * 1024 * 1024, 'ASR audio chunk exceeds 24 MiB')
    if http is None:
        import requests
        http = requests.Session()
    headers = {'Authorization': 'Bearer ' + config['key'], 'Content-Type': 'application/json'}
    with lock(folder):
        record_path = folder / 'task.json'
        record = read(record_path) if record_path.exists() else {'identity': identity(frozen), 'status': 'new'}
        require(record.get('identity') == identity(frozen), 'ASR audio, account or model changed; keep the original job')
        result_path = folder / 'transcript.json'
        if record['status'] == 'completed':
            require(result_path.is_file() and digest_file(result_path) == record.get('result_sha256'),
                    'Cached ASR result changed; do not resubmit')
            result = read(result_path)
            return {**result, 'cache_hit': True}
        if record['status'] in {'submitting', 'submission_unknown'}:
            raise ASRError('上次 ASR 受理状态不明；请核对云端记录，不会自动重复提交', unknown=True)
        if record['status'] in {'rejected', 'failed'}:
            raise ASRError('原 ASR 任务已失败；保留原记录，不自动重新提交', task_id=record.get('task_id'))
        try:
            if not record.get('task_id'):
                if not record.get('_file_url') or time.time() - record.get('uploaded_at', 0) > 160000:
                    policy = _json(http.get(config['base'] + '/uploads', params={'action': 'getPolicy', 'model': config['model']},
                                            headers=headers, timeout=(15, 45), allow_redirects=False), config)
                    policy = policy.get('data') or policy
                    host = _url(str(policy.get('upload_host', '')))
                    object_key = str(policy['upload_dir']).rstrip('/') + '/' + uuid.uuid4().hex + audio.suffix
                    fields = {'OSSAccessKeyId': policy['oss_access_key_id'], 'Signature': policy['signature'],
                              'policy': policy['policy'], 'key': object_key, 'success_action_status': '200',
                              'x-oss-object-acl': 'private', 'x-oss-forbid-overwrite': 'true'}
                    with audio.open('rb') as stream:
                        response = http.post(host, data=fields, files={'file': ('audio' + audio.suffix, stream)},
                                             timeout=(15, 300), allow_redirects=False)
                    require(response.status_code in {200, 201, 204}, 'ASR audio upload failed')
                    record.update(status='uploaded', _file_url='oss://' + object_key, uploaded_at=time.time())
                    save(record_path, record)
                record['status'] = 'submitting'
                save(record_path, record)
                try:
                    response = http.post(config['base'] + '/services/audio/asr/transcription',
                        headers={**headers, 'X-DashScope-Async': 'enable', 'X-DashScope-OssResourceResolve': 'enable'},
                        json={'model': config['model'], 'input': {'file_urls': [record['_file_url']]},
                              'parameters': {'channel_id': [0]}}, timeout=(15, 60), allow_redirects=False)
                    if 400 <= response.status_code < 500:
                        record['status'] = 'rejected'; save(record_path, record)
                    data = _json(response, config)
                    task_id = (data.get('output') or {}).get('task_id')
                    require(isinstance(task_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,160}', task_id),
                            'ASR submission returned no valid task ID')
                except Exception:
                    if record['status'] != 'rejected':
                        record['status'] = 'submission_unknown'; save(record_path, record)
                    raise
                record.update(status='accepted', task_id=task_id, request_id=data.get('request_id'))
                save(record_path, record)
            deadline = time.monotonic() + timeout
            raw_path = folder / 'provider-result.json'
            while not record.get('_transcription_url'):
                if time.monotonic() >= deadline:
                    raise ASRError('ASR 仍在处理；任务 ID 已保存，重新运行只继续查询', task_id=record['task_id'])
                data = _json(http.get(config['base'] + '/tasks/' + record['task_id'], headers=headers,
                                      timeout=(15, 60), allow_redirects=False), config)
                output = data.get('output') or {}
                if output.get('task_status') in {'FAILED', 'CANCELED'}:
                    record['status'] = 'failed'; save(record_path, record)
                    raise ASRError('原云端 ASR 任务失败；保留任务 ID，不重新提交', task_id=record['task_id'])
                if output.get('task_status') != 'SUCCEEDED':
                    time.sleep(poll_seconds); continue
                items = output.get('results') or []
                require(items and items[0].get('subtask_status') != 'FAILED' and items[0].get('transcription_url'),
                        'ASR returned no successful result file')
                record.update(_transcription_url=_url(items[0]['transcription_url']), usage=data.get('usage', {}))
                save(record_path, record)
            if not raw_path.exists():
                response = http.get(record['_transcription_url'], timeout=(15, 180), allow_redirects=False)
                require(response.status_code == 200, 'ASR result download failed; resume the same task')
                raw = response.json()
                save(raw_path, raw)
            segments = normalize(read(raw_path), duration)
            result = {'schema': 'jy-cloud-asr/v1', 'provider': 'bailian', 'model': config['model'],
                      'task_id': record['task_id'], 'timestamp_unit': 'seconds', 'segments': segments,
                      'usage': record.get('usage', {}), 'cost_cny': None, 'cache_hit': False,
                      'audio_sha256': frozen['audio_sha256']}
            save(result_path, result)
            record.update(status='completed', result_sha256=digest_file(result_path))
            save(record_path, record)
            return result
        except Exception as error:
            raise ASRError(safe_error(error, config), accepted=bool(record.get('task_id')),
                           task_id=record.get('task_id'), unknown=record['status'] in {'submitting', 'submission_unknown'}) from None
