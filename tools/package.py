"""Source-only ZIP, excluding models, credentials, environments and caches."""
import hashlib
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'extension/manifest.json').read_text(encoding='utf-8'))
assert manifest['manifest_version'] == 3
for name in ['background.js', 'popup.html', 'offscreen.html', 'pcm-worklet.js', 'content.js']:
    assert (root / 'extension' / name).exists()
destination = root.parent / ('CaptionCraft-Full-v' + manifest['version'] + '.zip')
skip = {'.venv', 'models', '__pycache__', '.git', '.cache', '.backup'}
with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
    for file in sorted(root.rglob('*')):
        relative = file.relative_to(root)
        if not file.is_file() or any(p in skip for p in relative.parts) or relative.as_posix() in ('helper/config.json', 'Local-Pairing.txt') or file.suffix in ('.pyc', '.log'):
            continue
        name = 'captioncraft/' + relative.as_posix()
        if relative.as_posix() == 'extension/config.js':
            archive.writestr(name, 'globalThis.LOCAL_CONFIG = {token: "", endpoint: "http://127.0.0.1:8765"};\n')
        else:
            archive.write(file, name)
with zipfile.ZipFile(destination) as archive:
    assert archive.testzip() is None
print(destination)
print('SHA256:', hashlib.sha256(destination.read_bytes()).hexdigest())
