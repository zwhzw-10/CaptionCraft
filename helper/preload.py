"""Progressive subtitle preparation, optional local translation and priority seek."""
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from language_settings import SOURCE_LANGUAGES, normalize_settings, cache_suffix
from local_translate import LocalTranslator
from audio_chunks import decode_window, audio_duration

CHUNK_SECONDS = 30

def video_id(url):
    p = urlparse(url)
    if p.scheme != 'https' or p.hostname not in ('www.youtube.com', 'youtube.com', 'youtu.be'):
        raise ValueError('Only HTTPS YouTube video URLs are supported')
    value = p.path.strip('/') if p.hostname == 'youtu.be' else (parse_qs(p.query).get('v', [''])[0] if p.path == '/watch' else p.path.split('/')[2] if p.path.startswith('/shorts/') else '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', value):
        raise ValueError('Invalid video ID')
    return value

def make_cues(segments, language='en'):
    cues = []
    compact = language in ('ja', 'zh')
    for segment in segments:
        if segment.no_speech_prob >= .6:
            continue
        words = getattr(segment, 'words', None)
        if not words:
            if segment.text.strip():
                cues.append({'start': segment.start, 'end': segment.end, 'text': segment.text.strip()})
            continue
        group = []
        def flush():
            if group:
                text = ''.join(w.word for w in group).strip() if compact else ' '.join(w.word.strip() for w in group)
                cues.append({'start': max(0, group[0].start), 'end': max(group[0].start + .15, group[-1].end + .15), 'text': text})
                group.clear()
        for word in words:
            if not word.word.strip():
                continue
            if group and (word.start - group[0].start > 4 or word.start - group[-1].end > .8):
                flush()
            group.append(word)
            if sum(len(w.word.strip()) for w in group) >= (32 if compact else 70) or word.word.rstrip().endswith(('.', '?', '!', '。', '！', '？')):
                flush()
        flush()
    cues.sort(key=lambda c: c['start'])
    for a, b in zip(cues, cues[1:]):
        a['end'] = min(a['end'], b['start'])
    return [c for c in cues if c['end'] > c['start']]

def parse_json3(data):
    cues = []
    for event in data.get('events', []):
        text = ''.join(s.get('utf8', '') for s in event.get('segs', [])).strip()
        if not text or not event.get('dDurationMs'):
            continue
        start = event.get('tStartMs', 0) / 1000
        end = start + event['dDurationMs'] / 1000
        cues.append({'start': start, 'end': end, 'text': text})
    cues.sort(key=lambda c: c['start'])
    for a, b in zip(cues, cues[1:]):
        a['end'] = min(a['end'], b['start'])
    return [c for c in cues if c['end'] > c['start']]

def merged_ranges(completed, duration):
    result = []
    for index in sorted(completed):
        start, end = index * CHUNK_SECONDS, min(duration, (index + 1) * CHUNK_SECONDS)
        if result and start <= result[-1][1] + .01:
            result[-1][1] = end
        else:
            result.append([start, end])
    return result

def pick_chunk(completed, count, priority):
    start = max(0, min(count - 1, int(priority // CHUNK_SECONDS)))
    return next((i for i in list(range(start, count)) + list(range(start)) if i not in completed), None)

def find_downloaded_audio(folder, info, guessed, finished):
    folder = Path(folder).resolve()
    candidates = [info.get('filepath'), info.get('_filename'), *finished]
    for item in info.get('requested_downloads') or []:
        candidates.extend([item.get('filepath'), item.get('_filename'), item.get('filename')])
    candidates.extend([guessed, *folder.glob('audio.*')])
    for value in candidates:
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute():
            path = folder / path
        path = path.resolve()
        if not path.is_relative_to(folder) or path.suffix.lower() not in {'.m4a', '.webm', '.mp4', '.opus', '.ogg', '.mp3', '.wav', '.aac', '.flac'}:
            continue
        if path.is_file() and path.stat().st_size:
            return path
    files = ', '.join(p.name for p in folder.iterdir()) or 'none'
    raise RuntimeError(f'No completed audio found (temporary files: {files}). Check download logs or import local audio.')

class Preloader:
    def __init__(self, root, model, model_lock, model_key='base'):
        self.root, self.model, self.lock, self.key = Path(root), model, model_lock, model_key
        self.guard = threading.Lock()
        self.cancelled = threading.Event()
        self.worker = None
        self.priority = 0
        self.job = {'state': 'idle', 'messageKey': 'idle', 'revision': 0, 'cues': []}
        self.translator = LocalTranslator(root)

    def status(self):
        with self.guard:
            return dict(self.job, cues=[dict(c) for c in self.job.get('cues', [])])

    def update(self, **data):
        with self.guard:
            self.job.update(data)
            self.job['revision'] = self.job.get('revision', 0) + 1

    def check(self):
        if self.cancelled.is_set():
            raise RuntimeError('Preparation cancelled')

    def cancel(self):
        self.cancelled.set()

    def prioritize(self, seconds):
        value = float(seconds)
        if not math.isfinite(value) or value < 0 or value > 10800:
            raise ValueError('Invalid playback position')
        with self.guard:
            self.priority = value

    def begin(self, url, uploaded=None, settings=None, position=0):
        vid = video_id(url)
        settings = normalize_settings(settings)
        position = float(position or 0)
        if not math.isfinite(position) or not 0 <= position <= 10800:
            raise ValueError('Invalid playback position')
        if self.key.endswith('.en') and settings['source'] != 'en':
            raise ValueError('Run Install.cmd to download the multilingual model, then use Start.cmd')
        with self.guard:
            if self.worker and self.worker.is_alive():
                raise RuntimeError('Previous job is stopping or still running; wait a moment')
            self.cancelled = threading.Event()
            self.priority = position
            self.job = {'state': 'downloading', 'messageKey': 'gettingAudio', 'videoId': vid,
                        'progress': 0, 'revision': 0, 'cues': [], 'readyRanges': [],
                        'display': settings['display'], 'target': settings['target'], 'complete': False}
            self.worker = threading.Thread(target=self.run, args=(vid, uploaded, settings), daemon=True)
            self.worker.start()
        return self.status()

    def atomic_cache(self, path, data):
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf8')
        temp.replace(path)

    def publish(self, chunks, original_done, duration, **data):
        cues = [dict(c) for index in sorted(chunks) for c in chunks[index]]
        translated = {i for i in original_done if not chunks.get(i) or all('translation' in c for c in chunks[i])}
        self.update(cues=cues, readyRanges=merged_ranges(original_done, duration),
                    translationRanges=merged_ranges(translated, duration), duration=duration, **data)

    def existing_subtitles(self, vid, source):
        from yt_dlp import YoutubeDL
        runtime = Path(os.environ.get('CAPTIONCRAFT_DENO', str(self.root / 'tools/deno/deno.exe')))
        options = {'quiet': True, 'no_warnings': True, 'skip_download': True, 'noplaylist': True,
                   'socket_timeout': 20, 'cachedir': str(self.root / '.cache/yt-dlp')}
        if runtime.exists():
            options['js_runtimes'] = {'deno': {'path': str(runtime)}}
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(f'https://www.youtube.com/watch?v={vid}', download=False)
            if not info or info.get('is_live'):
                raise ValueError('Live or unavailable video')
            duration = float(info.get('duration') or 0)
            if duration > 10800:
                raise ValueError('Video exceeds the 3-hour limit')
            # Never use YouTube's translated tracks as the purported original.
            language = source if source != 'auto' else str(info.get('language') or '').split('-')[0]
            for tracks in (info.get('subtitles') or {}, info.get('automatic_captions') or {}):
                keys = [k for k in tracks if k.split('-')[0] == language and 'orig' in k] + [k for k in tracks if k == language]
                if source == 'auto' and not language:
                    keys = [k for k in tracks if 'orig' in k and k.split('-')[0] in SOURCE_LANGUAGES]
                for key in dict.fromkeys(keys):
                    code = key.split('-')[0]
                    if code not in SOURCE_LANGUAGES:
                        continue
                    entry = next((t for t in tracks[key] if t.get('ext') == 'json3' and 'tlang=' not in t.get('url', '')), None)
                    if not entry:
                        continue
                    with ydl.urlopen(entry['url']) as response:
                        raw = response.read(10 * 1024 * 1024 + 1)
                    if len(raw) > 10 * 1024 * 1024:
                        continue
                    cues = parse_json3(json.loads(raw))
                    if cues:
                        return {'cues': cues, 'language': code, 'duration': max(duration, cues[-1]['end']), 'source': 'existing'}
        return None

    def run(self, vid, uploaded, settings):
        chunks, original_done = {}, set()
        duration = 0
        try:
            cache = self.root / '.cache/captions'
            cache.mkdir(parents=True, exist_ok=True)
            upload_id = '-file-' + hashlib.sha256(uploaded).hexdigest()[:16] if uploaded is not None else ''
            prefix = vid + upload_id + '-' + cache_suffix(settings, self.key)
            original_cache = cache / (prefix + '-original.json')
            translated_cache = cache / (prefix + '-' + settings['target'] + '-translated.json')
            existing = None
            if original_cache.exists():
                existing = json.loads(original_cache.read_text(encoding='utf8'))
            elif uploaded is None and settings['preferExisting']:
                self.update(messageKey='checkingExisting')
                try:
                    existing = self.existing_subtitles(vid, settings['source'])
                except Exception as exc:
                    print('Existing subtitle fallback:', type(exc).__name__, flush=True)
            self.check()
            if existing and settings['display'] != 'original' and translated_cache.exists():
                saved = json.loads(translated_cache.read_text(encoding='utf8'))
                self.update(state='ready', messageKey='cached', progress=100, complete=True,
                            duration=saved['duration'], language=saved['language'], cues=saved['cues'],
                            readyRanges=[[0, saved['duration']]])
                return
            jobs = self.root / '.cache/jobs'
            jobs.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=jobs) as directory:
                folder = Path(directory)
                path = None
                if existing:
                    duration, language = existing['duration'], existing['language']
                    for cue in existing['cues']:
                        index = min(max(0, int(cue['start'] // CHUNK_SECONDS)), max(0, math.ceil(duration / CHUNK_SECONDS) - 1))
                        chunks.setdefault(index, []).append(dict(cue))
                    original_done = set(range(math.ceil(duration / CHUNK_SECONDS)))
                    self.publish(chunks, original_done, duration, language=language, state='recognizing', messageKey='originalReady', origin=existing.get('source', 'cache'))
                else:
                    if uploaded is not None:
                        path = folder / 'uploaded-audio'
                        path.write_bytes(uploaded)
                        uploaded = None
                    else:
                        self.update(messageKey='gettingAudio')
                        path = self.download(vid, folder)
                    self.check()
                    duration = audio_duration(path)
                    if not duration or duration <= 0:
                        raise ValueError('Audio duration unavailable; use another audio file')
                    if duration > 10800:
                        raise ValueError('Video exceeds the 3-hour limit')
                    language = settings['source'] if settings['source'] != 'auto' else None
                count = math.ceil(duration / CHUNK_SECONDS)
                completed = set()
                translation_route = None
                self.update(language=language, duration=duration)
                while len(completed) < count:
                    self.check()
                    with self.guard:
                        priority = self.priority
                    index = pick_chunk(completed, count, priority)
                    core_start, core_end = index * CHUNK_SECONDS, min(duration, (index + 1) * CHUNK_SECONDS)
                    if index not in original_done:
                        self.update(state='recognizing', messageKey='recognizing', processingAt=core_start)
                        start, end = max(0, core_start - 1), min(duration, core_end + 1)
                        pcm = decode_window(path, start, end)
                        while not self.lock.acquire(timeout=.5):
                            self.check()
                        try:
                            segments, info = self.model.transcribe(pcm, language=language, task='transcribe',
                                beam_size=2, vad_filter=True, word_timestamps=True, condition_on_previous_text=False)
                            segments = list(segments)
                        finally:
                            self.lock.release()
                        self.check()
                        if language is None and any(s.text.strip() and s.no_speech_prob < .6 for s in segments):
                            language = info.language
                            if language not in SOURCE_LANGUAGES:
                                raise ValueError('Detected language is outside the six supported languages; select video language manually')
                        cues = make_cues(segments, language or 'en')
                        absolute = []
                        for cue in cues:
                            a, b = cue['start'] + start, cue['end'] + start
                            # Overlap permits recognition across boundaries; clip each core once.
                            if (a + b) / 2 < core_start or (a + b) / 2 >= core_end:
                                continue
                            cue.update(start=max(core_start, a), end=min(core_end, b))
                            if cue['end'] > cue['start']:
                                absolute.append(cue)
                        chunks[index] = absolute
                        original_done.add(index)
                        self.publish(chunks, original_done, duration, language=language, messageKey='partialReady', progress=round(len(original_done) / count * 100))
                        if len(original_done) == count:
                            original = {'duration': duration, 'language': language, 'source': 'local',
                                        'cues': [{k: v for k, v in c.items() if k != 'translation'} for i in sorted(chunks) for c in chunks[i]]}
                            self.atomic_cache(original_cache, original)
                    if settings['display'] != 'original' and language and chunks.get(index):
                        if translation_route is None:
                            translation_route = self.translator.ensure(language, settings['target'], self.check, self.update)
                            self.update(pivot=len(translation_route) > 1)
                        self.update(state='translating', messageKey='translating', processingAt=core_start)
                        texts = self.translator.translate([c['text'] for c in chunks[index]], translation_route, self.check)
                        for cue, text in zip(chunks[index], texts):
                            cue['translation'] = text
                    completed.add(index)
                    self.publish(chunks, original_done, duration, messageKey='partialReady', state='recognizing', progress=round(len(completed) / count * 100))
                if not any(chunks.values()):
                    raise ValueError('No speech recognized; check the selected language and audio')
                if existing and not original_cache.exists():
                    self.atomic_cache(original_cache, existing)
                if settings['display'] != 'original':
                    self.atomic_cache(translated_cache, {'duration': duration, 'language': language,
                        'cues': [c for i in sorted(chunks) for c in chunks[i]]})
                self.check()
                self.publish(chunks, original_done, duration, state='ready', messageKey='ready', complete=True, progress=100)
        except Exception as exc:
            state = 'cancelled' if self.cancelled.is_set() else 'error'
            print('Preparation:', state, type(exc).__name__, str(exc), flush=True)
            self.publish(chunks, original_done, duration, state=state, messageKey=state, error=str(exc)[:500])

    def download(self,vid,folder):
        try: from yt_dlp import YoutubeDL
        except ImportError: raise RuntimeError('Run Enable-Preload.cmd first')
        runtime=Path(os.environ.get('CAPTIONCRAFT_DENO', str(self.root/'tools/deno/deno.exe')))
        js={'deno':{'path':str(runtime)}} if runtime.exists() else {'node':{'path':shutil.which('node')}} if shutil.which('node') else {}
        if not js: raise RuntimeError('Run Enable-Preload.cmd to install JavaScript runtime')
        notes = []
        finished = []
        class Logger:
            def debug(self,message):
                if any(term in message.lower() for term in ('max-filesize', 'larger than', 'skipping download')):
                    notes.append(message); print('Audio download:',message,flush=True)
            def warning(self,message): print('Audio warning:',message,flush=True)
            def error(self,message): print('Audio error:',message,flush=True)
        def hook(info):
            self.check()
            if info.get('status') == 'finished' and info.get('filename'): finished.append(info['filename'])
            if info.get('downloaded_bytes',0)>200*1024*1024: raise RuntimeError('Audio exceeds 200 MB')
            total=info.get('total_bytes') or info.get('total_bytes_estimate') or 0
            self.update(messageKey='downloading',progress=min(99,round(info.get('downloaded_bytes',0)/total*100)) if total else 0)
        def filter_video(info,**_):
            self.check()
            if info.get('is_live'): raise ValueError('Live streams are not supported')
            if (info.get('duration') or 0)>10800: raise ValueError('Video exceeds the 3-hour limit')
        options={'format':'bestaudio[ext=m4a]/bestaudio','noplaylist':True,'outtmpl':str(folder/'audio.%(ext)s'),
            'max_filesize':200*1024*1024,'socket_timeout':20,'retries':2,'fragment_retries':2,'progress_hooks':[hook],
            'match_filter':filter_video,'logger':Logger(),'js_runtimes':js,'quiet':True,'cachedir':str(self.root/'.cache/yt-dlp')}
        with YoutubeDL(options) as downloader:
            info=downloader.extract_info(f'https://www.youtube.com/watch?v={vid}',download=True)
            if info is None: raise RuntimeError('Video filtered or unavailable')
            guessed=downloader.prepare_filename(info)
        try:
            return find_downloaded_audio(folder,info,guessed,finished)
        except RuntimeError:
            if notes: raise RuntimeError('Audio download skipped: ' + notes[-1][:300])
            raise
