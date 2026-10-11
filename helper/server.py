"""Loopback-only PCM transcription service. No audio files or transcript logs."""
import argparse
import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(os.environ.get('CAPTIONCRAFT_HOME', str(Path(__file__).resolve().parents[1])))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from language_settings import normalize_settings, SOURCE_LANGUAGES
MAX_BYTES = 16000 * 4 * 8


def make_handler(model, token, np, preloader=None, model_lock=None):
    lock = model_lock or threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'

        def log_message(self, *_):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def origin_ok(self):
            origin = self.headers.get('Origin', '')
            return not origin or (origin.startswith('chrome-extension://') and
                                  len(origin.removeprefix('chrome-extension://')) == 32 and
                                  all('a' <= c <= 'p' for c in origin.removeprefix('chrome-extension://')))

        def reply(self, code, data):
            body = json.dumps(data).encode('utf-8')
            self.send_response(code)
            origin = self.headers.get('Origin')
            if origin and self.origin_ok():
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        def authorized(self):
            if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}' or not self.origin_ok():
                self.reply(403, {'error': 'Origin/Host rejected'})
                return False
            if not hmac.compare_digest(self.headers.get('X-Local-Token', ''), token):
                self.reply(401, {'error': 'Assistant pairing mismatch; reconnect the extension'})
                return False
            return True

        def do_OPTIONS(self):
            if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}' or not self.origin_ok():
                return self.reply(403, {'error': 'Origin rejected'})
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', self.headers.get('Origin', 'null'))
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Local-Token, X-Video-URL, X-Caption-Options')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.send_header('Content-Length', '0')
            self.end_headers()

        def do_GET(self):
            if not self.authorized():
                return
            if self.path == '/prepare/status' and preloader:
                return self.reply(200, preloader.status())
            if self.path != '/health':
                return self.reply(404, {'error': 'Not found'})
            self.reply(200, {'ok': True, 'sample_rate': 16000, 'languages': list(SOURCE_LANGUAGES), 'version': '0.6.0'})

        def do_POST(self):
            if not self.authorized():
                return
            if self.path.startswith('/prepare') and preloader:
                return self.prepare()
            if self.path != '/transcribe':
                return self.reply(404, {'error': 'Not found'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                return self.reply(400, {'error': 'Invalid length'})
            if size < 4 or size > MAX_BYTES or size % 4:
                return self.reply(413, {'error': 'Expected <=8 seconds of float32 PCM'})
            if self.headers.get('Content-Type') != 'application/octet-stream':
                return self.reply(415, {'error': 'Expected application/octet-stream'})
            try:
                settings = normalize_settings(json.loads(self.headers.get('X-Caption-Options', '{}')))
                if settings['display'] != 'original':
                    return self.reply(400, {'error': 'Live mode currently supports original subtitles; use preparation for translation'})
            except (ValueError, TypeError) as exc:
                return self.reply(400, {'error': str(exc)})
            if not lock.acquire(blocking=False):
                return self.reply(429, {'error': 'Recognizer busy; wait or restart helper'})
            try:
                raw = self.rfile.read(size)
                if len(raw) != size:
                    return self.reply(400, {'error': 'Incomplete PCM'})
                pcm = np.frombuffer(raw, dtype='<f4').copy()
                if not np.isfinite(pcm).all() or np.max(np.abs(pcm)) > 1.01:
                    return self.reply(400, {'error': 'Invalid PCM samples'})
                started = time.perf_counter()
                text = ''
                words = []
                if float(np.sqrt(np.mean(pcm * pcm))) > 0.002:
                    segments, info = model.transcribe(pcm, language=None if settings['source'] == 'auto' else settings['source'], task='transcribe',
                        beam_size=1, vad_filter=True, condition_on_previous_text=False, word_timestamps=True,
                        vad_parameters={'min_silence_duration_ms': 400})
                    accepted = [s for s in segments if s.no_speech_prob < 0.6]
                    if getattr(info, 'language', settings['source']) not in SOURCE_LANGUAGES:
                        return self.reply(400, {'error': 'Detected language is outside the six supported source languages; select the audio language manually'})
                    text = ' '.join(s.text.strip() for s in accepted).strip()
                    for segment in accepted:
                        for word in (getattr(segment, 'words', None) or []):
                            words.append({'text': word.word, 'start': word.start, 'end': word.end})
                self.reply(200, {'text': text, 'words': words, 'language': getattr(locals().get('info'), 'language', settings['source']), 'seconds': time.perf_counter() - started})
            except Exception as exc:
                # Details remain local to this console; never log user audio/text.
                print('Transcription error:', type(exc).__name__, str(exc), flush=True)
                self.reply(500, {'error': 'Recognition failed; check helper console'})
            finally:
                lock.release()

        def prepare(self):
            try:
                if self.path == '/prepare/cancel':
                    preloader.cancel()
                    return self.reply(200, {'ok': True})
                if self.path == '/prepare/seek':
                    size = int(self.headers.get('Content-Length', '0'))
                    if size < 1 or size > 4096: return self.reply(400, {'error': 'Invalid seek input'})
                    data = json.loads(self.rfile.read(size))
                    preloader.prioritize(data['seconds'])
                    return self.reply(200, {'ok': True})
                upload = self.path == '/prepare/upload'
                if self.path not in ('/prepare', '/prepare/upload'):
                    return self.reply(404, {'error': 'Not found'})
                size = int(self.headers.get('Content-Length', '0'))
                if size < 1 or size > (200*1024*1024 if upload else 4096):
                    return self.reply(413, {'error': 'Input too large'})
                body = self.rfile.read(size)
                if len(body) != size:
                    return self.reply(400, {'error': 'Incomplete input'})
                data = json.loads(self.headers.get('X-Caption-Options', '{}')) if upload else json.loads(body)
                url = self.headers.get('X-Video-URL', '') if upload else data['url']
                settings = normalize_settings(data.get('settings', data) if upload else data.get('settings'))
                return self.reply(202, preloader.begin(url, body if upload else None, settings=settings, position=data.get('position', 0)))
            except (ValueError, KeyError, TypeError) as exc:
                return self.reply(400, {'error': str(exc)})
            except RuntimeError as exc:
                return self.reply(409, {'error': str(exc)})

    return Handler


def main():
    os.environ.setdefault('HF_HOME', str(ROOT / '.cache' / 'huggingface'))
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=['base.en', 'tiny.en', 'tiny', 'base', 'small'], default='base')
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--allow-download', action='store_true')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    import numpy as np
    from faster_whisper import WhisperModel
    config_file = ROOT / 'helper' / 'config.json'
    if not config_file.exists():
        raise SystemExit('Run Install.cmd first.')
    token = json.loads(config_file.read_text(encoding='utf-8'))['token']
    if len(token) < 32:
        raise SystemExit('Invalid token. Run Install.cmd.')
    print('Loading', args.model, '(first installation downloads model)...', flush=True)
    model = WhisperModel(args.model, device='cpu', compute_type='int8',
        cpu_threads=max(1, min(8, (os.cpu_count() or 2) - 1)),
        download_root=str(ROOT / 'models'), local_files_only=not (args.download or args.allow_download))
    # VAD skips silence: warm inference separately so READY verifies the model too.
    list(model.transcribe(np.zeros(16000, dtype=np.float32), language='en', beam_size=1, vad_filter=False)[0])
    list(model.transcribe(np.zeros(16000, dtype=np.float32), language='en', vad_filter=True)[0])
    if args.download:
        print('Model downloaded and inference warm-up passed.', flush=True)
        return
    from preload import Preloader
    model_lock = threading.Lock()
    preloader = Preloader(ROOT, model, model_lock, args.model)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(model, token, np, preloader, model_lock))
    server.daemon_threads = True
    print(f'READY: http://127.0.0.1:{args.port} | Multilingual | CPU int8 | Ctrl+C to stop', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
