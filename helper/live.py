"""Single, bounded live session; English streaming ASR and independent translation."""
import hashlib
import json
import math
import secrets
import tarfile
import threading
import time
import urllib.request
from pathlib import Path
from language_settings import normalize_settings
from local_translate import LocalTranslator

MODEL_URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-20M-2023-02-17.tar.bz2'
MODEL_SHA256 = '9c559283e8498d3fe95913c79ca1cb454bb26281ac2b102b41306c7d752765d9'
MODEL_FILES = {'tokens.txt': 5048, 'encoder-epoch-99-avg-1.int8.onnx': 42845182,
               'decoder-epoch-99-avg-1.int8.onnx': 539499, 'joiner-epoch-99-avg-1.int8.onnx': 259572}


def stream_settings(value):
    settings = normalize_settings(value)
    engine = value.get('liveEngine', 'auto')
    if engine not in ('auto', 'sherpa', 'whisper'):
        raise ValueError('Unsupported live engine')
    if engine == 'sherpa' and settings['source'] != 'en':
        raise ValueError('English streaming requires English as the audio language')
    settings['engine'] = 'sherpa' if engine == 'sherpa' or (engine == 'auto' and settings['source'] == 'en') else 'whisper'
    return settings


class Live:
    def __init__(self, root, translator=None):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.decode_lock = threading.Lock()
        self.session = None
        self.recognizer = None
        self.stream = None
        self.loader = False
        self.model_state = {'state': 'idle', 'downloadMB': None}
        self.translation = {'state': 'idle'}
        self.pending = None
        self.worker = False
        self.latest_revision = -1
        self.translator = translator or LocalTranslator(root)

    def status(self):
        with self.lock:
            return {**self.model_state, 'session': self.session,
                    'engine': self.settings['engine'] if hasattr(self, 'settings') else None}

    def prepare(self, value):
        settings = stream_settings(value)
        with self.lock:
            self.session = secrets.token_urlsafe(24)
            self.settings = settings
            self.stream = None
            self.processed = None
            self.utterance = 0
            self.last_sequence = -1
            self.pending = None
            self.latest_revision = -1
            self.translation = {'state': 'idle', 'session': self.session}
            if settings['engine'] == 'whisper' or self.recognizer is not None:
                self.model_state = {'state': 'ready', 'downloadMB': None}
            elif not self.loader:
                self.model_state = {'state': 'loading', 'downloadMB': 0}
                self.loader = True
                threading.Thread(target=self.load_streaming, daemon=True).start()
            else:
                self.model_state = {'state': 'loading', 'downloadMB': self.model_state.get('downloadMB')}
            return self.status()

    def load_streaming(self):
        try:
            folder = self.root / 'models/live-english-20m'
            folder.mkdir(parents=True, exist_ok=True)
            if not all((folder / name).is_file() and (folder / name).stat().st_size == size for name, size in MODEL_FILES.items()):
                archive = folder / 'model.download'
                try:
                    digest = hashlib.sha256()
                    total = 0
                    with urllib.request.urlopen(urllib.request.Request(MODEL_URL, headers={'User-Agent': 'CaptionCraft/0.7'}), timeout=45) as source, archive.open('wb') as out:
                        while block := source.read(256 * 1024):
                            total += len(block)
                            if total > 160 * 1024 * 1024:
                                raise ValueError('Streaming model download too large')
                            digest.update(block)
                            out.write(block)
                            with self.lock:
                                self.model_state['downloadMB'] = round(total / 1048576, 1)
                    if digest.hexdigest() != MODEL_SHA256:
                        raise ValueError('Streaming model checksum mismatch')
                    with tarfile.open(archive) as package:
                        seen = set()
                        for item in package.getmembers():
                            # Never extract paths from an archive or execute scripts.
                            name = Path(item.name).name
                            if name not in MODEL_FILES:
                                continue
                            if not item.isfile() or name in seen or item.size != MODEL_FILES[name]:
                                raise ValueError('Invalid streaming model archive')
                            seen.add(name)
                            data = package.extractfile(item).read()
                            temp = folder / (name + '.tmp')
                            temp.write_bytes(data)
                            temp.replace(folder / name)
                        if seen != set(MODEL_FILES):
                            raise ValueError('Streaming model incomplete')
                finally:
                    archive.unlink(missing_ok=True)
            import sherpa_onnx
            recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                tokens=str(folder / 'tokens.txt'), encoder=str(folder / 'encoder-epoch-99-avg-1.int8.onnx'),
                decoder=str(folder / 'decoder-epoch-99-avg-1.int8.onnx'), joiner=str(folder / 'joiner-epoch-99-avg-1.int8.onnx'),
                num_threads=2, provider='cpu', sample_rate=16000, feature_dim=80, decoding_method='greedy_search',
                enable_endpoint_detection=True, rule1_min_trailing_silence=2.4,
                rule2_min_trailing_silence=.8, rule3_min_utterance_length=20)
            with self.lock:
                self.recognizer = recognizer
                self.model_state = {'state': 'ready', 'downloadMB': None}
        except Exception as exc:
            with self.lock:
                self.model_state = {'state': 'error', 'error': 'Streaming model unavailable; check your network or select Whisper. ' + type(exc).__name__}
        finally:
            with self.lock:
                self.loader = False

    def validate(self, value):
        with self.lock:
            if not self.session or value.get('session') != self.session:
                raise ValueError('Live session expired; restart real-time captions')

    def push(self, pcm, value, np):
        self.validate(value)
        start, end = value.get('start'), value.get('end')
        sequence = value.get('sequence')
        if not isinstance(sequence, int) or sequence < 0 or not all(isinstance(n, (int, float)) and math.isfinite(n) and n >= 0 for n in (start, end)):
            raise ValueError('Invalid streaming timestamps')
        if abs(end - start - len(pcm) / 16000) > .002:
            raise ValueError('Streaming frame duration mismatch')
        started = time.perf_counter()
        with self.decode_lock, self.lock:
            self.validate(value)
            if self.settings['engine'] != 'sherpa' or self.recognizer is None:
                raise ValueError('Streaming recognizer is not ready')
            if sequence <= self.last_sequence:
                raise ValueError('Out-of-order streaming frame')
            self.last_sequence = sequence
            gap = self.processed is not None and start > self.processed + .01
            if self.stream is None or gap or (self.processed is not None and end < self.processed):
                self.stream = self.recognizer.create_stream()
                self.utterance += 1
                self.processed = start
            skip = max(0, round((self.processed - start) * 16000))
            new = pcm[skip:]
            if len(new):
                self.stream.accept_waveform(16000, new)
                while self.recognizer.is_ready(self.stream):
                    self.recognizer.decode_stream(self.stream)
            self.processed = max(self.processed, end)
            result = self.recognizer.get_result(self.stream)
            text = (result.text if hasattr(result, 'text') else str(result)).strip()
            final = bool(self.recognizer.is_endpoint(self.stream))
            utterance = self.utterance
            if final:
                self.recognizer.reset(self.stream)
                self.utterance += 1
            return {'text': text, 'language': 'en', 'final': final, 'utterance': utterance,
                    'gap': gap, 'seconds': time.perf_counter() - started, 'engine': 'sherpa'}

    def close(self, value=None):
        with self.lock:
            if value and value.get('session') != self.session:
                return
            self.session = None
            self.stream = None
            self.pending = None
            self.translation = {'state': 'idle'}

    def queue_translation(self, value):
        self.validate(value)
        text, revision, language = value.get('text'), value.get('revision'), value.get('language')
        if not isinstance(text, str) or not 0 < len(text) <= 1200 or not isinstance(revision, int) or revision < 0:
            raise ValueError('Invalid live translation input')
        if language not in ('en', 'ja', 'fr', 'es', 'ko', 'ru', 'zh'):
            raise ValueError('Unsupported detected language')
        with self.lock:
            self.validate(value)
            if revision <= self.latest_revision:
                return {'ok': True, 'ignored': True}
            self.latest_revision = revision
            self.pending = {'session': self.session, 'revision': revision, 'text': text,
                            'language': language, 'target': self.settings['target']}
            if not self.worker:
                self.worker = True
                threading.Thread(target=self.translate_loop, daemon=True).start()
            return {'ok': True}

    def translation_status(self, session):
        self.validate({'session': session})
        with self.lock:
            return dict(self.translation)

    def translate_loop(self):
        while True:
            with self.lock:
                item, self.pending = self.pending, None
                if item is None:
                    self.worker = False
                    return
            def check():
                with self.lock:
                    if item['session'] != self.session:
                        raise ValueError('Translation session cancelled')
            def update(**data):
                with self.lock:
                    if item['session'] == self.session:
                        self.translation = {'state': 'working', **item, **data}
            try:
                check()
                update()
                route = self.translator.ensure(item['language'], item['target'], check=check, update=update)
                result = self.translator.translate([item['text']], route, check=check, beam_size=1)[0]
                check()
                with self.lock:
                    if item['session'] == self.session:
                        self.translation = {'state': 'ready', **item, 'translation': result}
            except Exception as exc:
                with self.lock:
                    if item['session'] == self.session:
                        self.translation = {'state': 'error', **item, 'error': 'Local translation unavailable: ' + str(exc)[:200]}
