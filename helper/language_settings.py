"""Language choices are independent of the viewer's locale."""
import json
from pathlib import Path
REGISTRY = json.loads((Path(__file__).resolve().parents[1] / 'shared/languages.json').read_text(encoding='utf8'))
SOURCE_LANGUAGES = tuple(REGISTRY['source'])
TARGET_LANGUAGES = tuple(REGISTRY['target'])

def normalize_settings(value=None):
    value = value or {}
    if not isinstance(value, dict):
        raise ValueError('Invalid language settings')
    source = value.get('source', 'auto')
    target = value.get('target', 'zh')
    display = value.get('display', 'original')
    if source not in ('auto',) + SOURCE_LANGUAGES:
        raise ValueError('Unsupported video language')
    if target not in TARGET_LANGUAGES:
        raise ValueError('Unsupported translation language')
    if display not in ('original', 'bilingual', 'translation'):
        raise ValueError('Unsupported subtitle display mode')
    return {'source': source, 'target': target, 'display': display,
            'preferExisting': value.get('preferExisting', True) is not False}

def cache_suffix(settings, model):
    # Original transcription and every translation are cached independently.
    return f"{model}-{settings['source']}-v5"
