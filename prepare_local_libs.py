"""Local dependency preparation and offline one-step application launch."""
import argparse
import base64
import csv
from datetime import datetime
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from local_dependencies import ROOT, LIBS, runtime_identity

# A fresh process with -S cannot access system site-packages. Besides imports,
# this checks Pillow's image operations, NumPy/OpenBLAS, and PDFium rendering.
VERIFY_CODE = '''
import io, json, socket, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from local_dependencies import activate_local_dependencies, MODULES
activate_local_dependencies(Path(sys.argv[2]))
def denied(*args, **kwargs):
    raise PermissionError('Dependency validation has no network access')
socket.socket = denied
socket.create_connection = denied
socket.getaddrinfo = denied
import numpy as np
from PIL import Image, ImageTk, _imagingtk
from pypdf import PdfWriter, PdfReader
import pypdfium2 as pdfium
import pypdfium2_raw
assert np.linalg.norm(np.array([3., 4.])) == 5.
assert np.fft.fft(np.ones(8))[0] == 8
image = Image.new('RGB', (8, 8), 'blue')
assert np.asarray(image).shape == (8, 8, 3)
writer = PdfWriter()
writer.add_blank_page(width=100, height=100)
stream = io.BytesIO()
writer.write(stream)
assert len(PdfReader(io.BytesIO(stream.getvalue())).pages) == 1
document = pdfium.PdfDocument(stream.getvalue())
page = document[0]
bitmap = page.render(scale=1)
assert bitmap.to_pil().size == (100, 100)
bitmap.close()
page.close()
document.close()
folder = Path(sys.argv[2]).resolve()
origins = {}
for name in MODULES:
    origin = Path(sys.modules[name].__file__).resolve()
    assert origin.is_relative_to(folder), (name, origin)
    origins[name] = str(origin.relative_to(folder))
print(json.dumps(origins))
'''


def pinned_requirements():
    packages = {}
    for line in (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)', line)
        if not match:
            raise ValueError('requirements.txt kesin sürümler içermeli: ' + line)
        packages[match[1]] = match[2]
    return packages


def copy_installed(packages, stage):
    """Copy distribution RECORD files, including native binaries and licenses."""
    for name, version in packages.items():
        distribution = metadata.distribution(name)
        if distribution.version != version:
            raise ValueError(f'{name}: kurulu sürüm {distribution.version}, gereken {version}.')
        files = distribution.files
        if not files:
            raise ValueError(f'{name}: kurulu dosya listesi bulunamadı.')
        records = []
        record_file = None
        for relative in files:
            # External console launchers are not application dependencies and
            # may embed an absolute interpreter path. Never copy outside libs.
            if relative.is_absolute() or '..' in relative.parts:
                continue
            if '__pycache__' in relative.parts or relative.suffix in ('.pyc', '.pyo'):
                continue
            source = Path(distribution.locate_file(relative))
            target = stage / relative
            if not target.resolve().is_relative_to(stage.resolve()):
                raise ValueError('Paket dosyası hazırlık klasörünün dışında.')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            # Redistributors may sign native files after wheel installation.
            # Verify exact copying against the installed file, then regenerate
            # RECORD for the actual bundle, excluding external console scripts.
            source_hash = hashlib.sha256(source.read_bytes()).digest()
            if hashlib.sha256(target.read_bytes()).digest() != source_hash:
                raise ValueError(f'Paket dosyası doğru kopyalanamadı: {name}/{relative}')
            if relative.name == 'RECORD' and relative.parent.name.endswith('.dist-info'):
                record_file = target
                records.append((str(relative).replace('\\', '/'), '', ''))
            else:
                digest = base64.urlsafe_b64encode(source_hash).rstrip(b'=').decode('ascii')
                records.append((str(relative).replace('\\', '/'), 'sha256=' + digest, target.stat().st_size))
        if record_file is not None:
            with record_file.open('w', encoding='utf-8', newline='') as handle:
                csv.writer(handle).writerows(records)


def prepare(args):
    if sys.implementation.name != 'cpython' or sys.version_info[:2] != (3, 12):
        raise ValueError('Hazırlık için CPython 3.12.x kullanın; hedefte aynı mimari olmalıdır.')
    if LIBS.is_symlink() or (hasattr(LIBS, 'is_junction') and LIBS.is_junction()):
        raise ValueError('libs gerçek bir proje klasörü olmalı; dosya bağlantısı kullanmayın.')
    if LIBS.exists() and not LIBS.is_dir():
        raise ValueError('libs adıyla bir dosya var. Klasör hazırlanamıyor.')
    populated = LIBS.is_dir() and any(LIBS.iterdir())
    if populated and not args.replace:
        raise ValueError('libs zaten dolu. Güncellemek için --replace kullanın; eski sürüm yedeklenir.')
    packages = pinned_requirements()
    # tempfile.mkdtemp uses owner-only ACLs on Windows. A bundle must inherit
    # the project's permissions so the normal desktop user can also read it.
    stage = ROOT / ('.libs-stage-' + uuid.uuid4().hex)
    stage.mkdir()
    try:
        if args.from_installed:
            copy_installed(packages, stage)
        else:
            command = [sys.executable, '-m', 'pip', '--disable-pip-version-check', 'install',
                       '--only-binary=:all:', '--no-compile', '--no-warn-script-location',
                       '-r', str(ROOT / 'requirements.txt'), '-t', str(stage)]
            if args.wheelhouse:
                wheelhouse = Path(args.wheelhouse).resolve(strict=True)
                if not wheelhouse.is_dir():
                    raise ValueError('Wheel klasörü gerekli.')
                command.extend(['--no-index', '--find-links', str(wheelhouse)])
            subprocess.run(command, check=True)
        (stage / 'arar_bundle.json').write_text(json.dumps({
            'runtime': runtime_identity(), 'packages': packages,
            'python_version': sys.version.split()[0],
            'prepared_with': 'installed-distributions' if args.from_installed else 'pip-target',
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        subprocess.run([sys.executable, '-S', '-B', '-c', VERIFY_CODE, str(ROOT), str(stage)], check=True)
        backup = None
        if LIBS.exists():
            suffix = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
            backup = ROOT / ('libs.backup-' + suffix)
            LIBS.rename(backup)
        try:
            stage.rename(LIBS)
        except OSError:
            if backup is not None:
                backup.rename(LIBS)
            raise
        print('Yerel bağımlılıklar hazır: libs/')
        print('Çevrimdışı başlatma: python main.py')
        if backup is not None:
            print('Önceki klasör korunuyor: ' + backup.name)
    finally:
        # Only this invocation's verified, project-local staging directory.
        if stage.exists() and stage.parent == ROOT and stage.name.startswith('.libs-stage-'):
            shutil.rmtree(stage)


def verify_local_bundle():
    result = subprocess.run(
        [sys.executable, '-S', '-B', '-c', VERIFY_CODE, str(ROOT), str(LIBS)],
        capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise ValueError('Yerel paketler kullanılamıyor:\n' + result.stderr.strip())


def launch(args):
    """Repair only from local sources. Launchers never use an online index."""
    if sys.implementation.name != 'cpython' or sys.version_info[:2] != (3, 12):
        raise ValueError('Başlatmak için Tkinter içeren CPython 3.12.x kullanın.')
    try:
        verify_local_bundle()
    except ValueError:
        print('Yerel bağımlılıklar hazırlanıyor…', flush=True)
        wheelhouse = Path(args.wheelhouse) if args.wheelhouse else ROOT / 'wheelhouse'
        if not args.from_installed and wheelhouse.is_dir() and any(wheelhouse.glob('*.whl')):
            source = argparse.Namespace(replace=True, from_installed=False, wheelhouse=str(wheelhouse))
        else:
            source = argparse.Namespace(replace=True, from_installed=True, wheelhouse=None)
        try:
            prepare(source)
        except (OSError, ValueError, metadata.PackageNotFoundError, subprocess.CalledProcessError) as exc:
            raise ValueError(
                'Otomatik çevrimdışı hazırlık tamamlanamadı. Bu bilgisayarda uyumlu '
                'libs, yerel wheel dosyaları veya aynı sürümlerde kurulu paketler gerekli. '
                'İnternete bağlanılmadı.\n' + str(exc)) from exc
    print('Arar başlatılıyor…', flush=True)
    if sys.platform == 'win32':
        pythonw = Path(sys.executable).with_name('pythonw.exe')
        if pythonw.is_file():
            subprocess.Popen([str(pythonw), '-B', str(ROOT / 'main.py')], cwd=ROOT)
            return 0
    return subprocess.run([sys.executable, '-B', str(ROOT / 'main.py')], cwd=ROOT).returncode


def main():
    parser = argparse.ArgumentParser(description='Arar için taşınabilir libs klasörünü hazırla.')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--from-installed', action='store_true', help='Doğrulanmış mevcut paketleri indirimsiz kopyala.')
    source.add_argument('--wheelhouse', help='Yalnızca bu yerel klasördeki wheel dosyalarını kullan.')
    parser.add_argument('--replace', action='store_true', help='Doğrulama sonrası mevcut libs klasörünü yedekle ve yenile.')
    parser.add_argument('--launch', action='store_true', help='Yerel paketleri otomatik kontrol et/hazırla ve Arar’ı çevrimdışı başlat.')
    args = parser.parse_args()
    try:
        if args.launch:
            return launch(args)
        prepare(args)
    except (OSError, ValueError, metadata.PackageNotFoundError, subprocess.CalledProcessError) as exc:
        print('Yerel bağımlılıklar hazırlanamadı: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
