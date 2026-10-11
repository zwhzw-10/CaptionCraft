import json
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / 'helper' / 'config.json'
token = json.loads(path.read_text(encoding='utf-8'))['token'] if path.exists() else secrets.token_urlsafe(32)
path.write_text(json.dumps({'token': token}), encoding='utf-8')
(root / 'extension' / 'config.js').write_text(
    'globalThis.LOCAL_CONFIG = ' + json.dumps({'token': token, 'endpoint': 'http://127.0.0.1:8765'}) + ';\n', encoding='utf-8')
print('Local pairing configured. Reload the extension after installation.')

(root/'Local-Pairing.txt').write_text(token + '\n',encoding='utf8')
