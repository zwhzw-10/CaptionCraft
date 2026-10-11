"""Optional real CPU + HTTP test; run after Install.cmd. No model downloads."""
import http.client
import importlib.util
import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['HF_HOME'] = str(ROOT / '.cache/huggingface')
import sys
sys.path.insert(0, str(ROOT / "helper"))
import sys
sys.path.insert(0, str(ROOT / "helper"))
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio


def main():
    model_path = os.environ.get('CAPTIONS_TEST_MODEL_DIR', str(ROOT / 'models'))
    model = WhisperModel('base', device='cpu', compute_type='int8', cpu_threads=4,
                         download_root=model_path, local_files_only=True)
    spec = importlib.util.spec_from_file_location('helper_server', ROOT/'helper/server.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    server = ThreadingHTTPServer(('127.0.0.1', 0), module.make_handler(model, 'test-token', np))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    samples = decode_audio(str(ROOT/'tests/sample-english.wav'), sampling_rate=16000)
    transcript = []
    try:
        for i in range(0, len(samples), 64000):
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=30)
            conn.request('POST', '/transcribe', samples[i:i+64000].astype('<f4').tobytes(),
                         {'Host': f'127.0.0.1:{server.server_port}', 'X-Local-Token': 'test-token', 'Content-Type': 'application/octet-stream'})
            response = conn.getresponse(); result = json.loads(response.read()); conn.close()
            assert response.status == 200, result
            transcript.append(result['text'])
            print(f"Block {i//64000+1}: {result['text']} | {result['seconds']:.3f}s", flush=True)
        text = ' '.join(transcript).lower()
        assert 'hello' in text and 'english' in text and 'fox' in text, text
        print('PASS: real CPU int8 model, bundled English sample, HTTP PCM recognition, offline load')
    finally:
        server.shutdown(); server.server_close()


if __name__ == '__main__':
    main()
