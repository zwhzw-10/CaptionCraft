"""Offline CTranslate2 inference using official Argos model data.

No remote translation service. Short caption units need no sentence splitter.
Only model/tokenizer data is extracted; downloaded executable code is never run.
"""
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse
from language_settings import TARGET_LANGUAGES

INDEX = 'https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json'
MAX_DOWNLOAD = 600 * 1024 * 1024
MAX_UNPACK = 1024 * 1024 * 1024

def route_for(index, source, target):
    if source == target:
        return []
    pairs = {(p.get('from_code'), p.get('to_code')): p for p in index
             if p.get('type', 'translate') == 'translate'}
    if (source, target) in pairs:
        return [pairs[source, target]]
    if (source, 'en') in pairs and ('en', target) in pairs:
        return [pairs[source, 'en'], pairs['en', target]]
    raise ValueError(f'No local translation model for {source} → {target}')

def unpack_model(archive, destination, source, target):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(archive) as package:
        total = 0
        for item in package.infolist():
            name = item.filename.replace('\\', '/')
            parts = Path(name).parts
            if name.startswith('/') or '..' in parts or any(':' in p for p in parts):
                raise ValueError('Unsafe model archive path')
            total += item.file_size
            if total > MAX_UNPACK:
                raise ValueError('Translation model archive too large')
        metadata_names = [i.filename for i in package.infolist()
                          if Path(i.filename).name == 'metadata.json']
        if len(metadata_names) != 1:
            raise ValueError('Invalid translation model metadata')
        prefix = metadata_names[0][:-len('metadata.json')]
        metadata = json.loads(package.read(metadata_names[0]))
        if metadata.get('from_code') != source or metadata.get('to_code') != target:
            raise ValueError('Translation model language mismatch')
        for item in package.infolist():
            if not item.filename.startswith(prefix) or item.is_dir():
                continue
            relative = item.filename[len(prefix):]
            if not (relative.startswith('model/') or relative in
                    ('metadata.json', 'sentencepiece.model', 'bpe.model', 'README.md', 'LICENSE')):
                continue
            path = (destination / relative).resolve()
            if not path.is_relative_to(destination):
                raise ValueError('Unsafe extraction target')
            path.parent.mkdir(parents=True, exist_ok=True)
            with package.open(item) as incoming, path.open('wb') as out:
                shutil.copyfileobj(incoming, out)
    if not (destination / 'model/model.bin').is_file():
        raise ValueError('Translation model data is missing')
    return metadata

class LocalTranslator:
    def __init__(self, root):
        self.root = Path(root) / 'models/translation'
        self.root.mkdir(parents=True, exist_ok=True)
        self.index = None
        self.engines = {}

    def get_index(self):
        if self.index is not None:
            return self.index
        cache = self.root / 'index.json'
        if cache.exists():
            self.index = json.loads(cache.read_text(encoding='utf8'))
            return self.index
        with urllib.request.urlopen(urllib.request.Request(INDEX, headers={'User-Agent':'Mozilla/5.0 CaptionCraft/0.5'}), timeout=30) as response:
            data = response.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise ValueError('Translation index too large')
        index = json.loads(data)
        if not isinstance(index, list):
            raise ValueError('Invalid translation index')
        cache.write_text(json.dumps(index), encoding='utf8')
        self.index = index
        return index

    def ensure(self, source, target, check=lambda: None, update=lambda **_: None):
        if source not in TARGET_LANGUAGES or target not in TARGET_LANGUAGES:
            raise ValueError('Unsupported translation language')
        if source == target:
            return []
        route = route_for(self.get_index(), source, target)
        wanted = {(p['from_code'], p['to_code']) for p in route}
        self.engines = {pair: engine for pair, engine in self.engines.items() if pair in wanted}
        for entry in route:
            check()
            a, b = entry['from_code'], entry['to_code']
            folder = self.root / f'{a}-{b}'
            if not (folder / 'model/model.bin').exists():
                update(state='model-download', messageKey='modelDownload', detail=f'{a} → {b}')
                links = [u for u in entry.get('links', []) if urlparse(u).scheme == 'https'
                         and urlparse(u).hostname in ('argos-net.com', 'www.argosopentech.com')]
                if not links:
                    raise ValueError('Official HTTPS model link unavailable')
                with tempfile.TemporaryDirectory(dir=self.root) as temp:
                    archive = Path(temp) / 'model.argosmodel'
                    with urllib.request.urlopen(urllib.request.Request(links[0], headers={'User-Agent':'Mozilla/5.0 CaptionCraft/0.5'}), timeout=60) as response, archive.open('wb') as out:
                        size = 0
                        while block := response.read(256 * 1024):
                            check()
                            size += len(block)
                            if size > MAX_DOWNLOAD:
                                raise ValueError('Translation download exceeds 600 MB')
                            out.write(block)
                            update(downloadMB=round(size / 1024 / 1024, 1))
                    staged = Path(temp) / 'extracted'
                    staged.mkdir()
                    unpack_model(archive, staged, a, b)
                    check()
                    if folder.exists():
                        # Only our exact language-model directory is replaced.
                        if folder.resolve().parent != self.root.resolve():
                            raise ValueError('Invalid model destination')
                        shutil.rmtree(folder)
                    staged.replace(folder)
            self.load(a, b)
        update(detail='', downloadMB=None)
        return [(p['from_code'], p['to_code']) for p in route]

    def load(self, source, target):
        key = (source, target)
        if key in self.engines:
            return self.engines[key]
        import ctranslate2
        folder = self.root / f'{source}-{target}'
        metadata = json.loads((folder / 'metadata.json').read_text(encoding='utf8'))
        if (folder / 'sentencepiece.model').exists():
            import sentencepiece
            tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(folder / 'sentencepiece.model'))
            encode = lambda text: tokenizer.encode(text, out_type=str)
            decode = lambda tokens: tokenizer.decode(tokens).replace('▁', ' ').replace('_', ' ')
        elif (folder / 'bpe.model').exists():
            from sacremoses import MosesTokenizer, MosesDetokenizer, MosesPunctNormalizer
            from subword_nmt.apply_bpe import BPE
            token = MosesTokenizer(source)
            detoken = MosesDetokenizer(target)
            normal = MosesPunctNormalizer(source)
            with (folder / 'bpe.model').open(encoding='utf8') as codes:
                bpe = BPE(codes)
            encode = lambda text: bpe.segment_tokens(token.tokenize(normal.normalize(text)))
            decode = lambda pieces: detoken.detokenize(' '.join(pieces).replace('@@ ', '').split())
        else:
            raise ValueError('Unsupported translation tokenizer')
        engine = ctranslate2.Translator(str(folder / 'model'), device='cpu', compute_type='int8',
                                      intra_threads=max(1, min(4, os.cpu_count() or 2)))
        self.engines[key] = (engine, encode, decode, metadata.get('target_prefix', ''))
        return self.engines[key]

    def translate(self, texts, route, check=lambda: None):
        result = list(texts)
        for source, target in route:
            engine, encode, decode, prefix = self.load(source, target)
            result_next = []
            for start in range(0, len(result), 8):
                check()
                batch = result[start:start + 8]
                options = {'beam_size': 4, 'replace_unknowns': True, 'length_penalty': .2}
                if prefix:
                    options['target_prefix'] = [[prefix]] * len(batch)
                outputs = engine.translate_batch([encode(t) for t in batch], **options)
                for output in outputs:
                    text = decode(output.hypotheses[0]).strip()
                    if prefix and text.startswith(prefix):
                        text = text[len(prefix):].strip()
                    result_next.append(text)
            result = result_next
        return result

