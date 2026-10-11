import json
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
try:
    token = json.loads((root/'helper/config.json').read_text(encoding='utf-8'))['token']
    # Explicitly bypass system proxy for loopback.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request('http://127.0.0.1:8765/health', headers={'X-Local-Token': token})
    with opener.open(req, timeout=5) as response:
        assert json.load(response)['ok']
    req = urllib.request.Request('http://127.0.0.1:8765/transcribe', data=bytes(64000*4),
        headers={'X-Local-Token': token, 'Content-Type': 'application/octet-stream'})
    with opener.open(req, timeout=30) as response:
        assert json.load(response)['text'] == ''
    print('PASS: helper connected, pairing token accepted, silence handled.')
    print('Next: open a YouTube video and click extension -> Start.')
except Exception as exc:
    print('FAIL:', str(exc))
    print('Keep Start.cmd open until READY. If token mismatch, rerun Install.cmd and reload extension.')
    raise SystemExit(1)
