"""Download the official Argos English→Chinese package; never sends documents."""
import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = 'https://argos-net.com/v1/translate-en_zh-1_9.argosmodel'

def main():
    target = ROOT / 'models' / 'en_zh'
    if (target / 'metadata.json').exists() and (target / 'model/model.bin').exists():
        print(f'Model already installed: {target}')
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        temp = Path(temp)
        archive = temp / 'model.zip'
        with urllib.request.urlopen(URL, timeout=120) as response, archive.open('wb') as output:
            shutil.copyfileobj(response, output)
        unpack = temp / 'unpack'
        with zipfile.ZipFile(archive) as package:
            if package.testzip() is not None:
                raise ValueError('Corrupt model archive')
            for entry in package.infolist():
                destination = (unpack / entry.filename).resolve()
                if not destination.is_relative_to(unpack.resolve()):
                    raise ValueError('Unsafe archive path')
            package.extractall(unpack)
        candidates = list(unpack.rglob('metadata.json'))
        if len(candidates) != 1:
            raise ValueError('Unexpected package structure')
        folder = candidates[0].parent
        metadata = json.loads(candidates[0].read_text())
        if (metadata['from_code'], metadata['to_code']) != ('en', 'zh'):
            raise ValueError('Wrong language pair')
        if not (folder / 'model/model.bin').exists() or not (folder / 'sentencepiece.model').exists():
            raise ValueError('Incomplete model package')
        if target.exists():
            raise ValueError(f'Incomplete existing model: {target}; inspect before replacing')
        shutil.move(str(folder), target)
    print(f'Installed: {target}')

if __name__ == '__main__':
    main()
