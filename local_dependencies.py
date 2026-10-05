"""Project-local imports; this module uses only the Python standard library."""
import importlib.util
import json
import platform
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parent
LIBS = ROOT / 'libs'
MODULES = ('PIL', 'numpy', 'pypdf', 'pypdfium2', 'pypdfium2_raw')
PREPARATION_HINT = (
    'Geliştirme bilgisayarında setup_offline_libs.bat veya setup_offline_libs.sh çalıştırın ve hazırlanan '
    'libs klasörünü projeyle birlikte taşıyın. Ayrıntılar: README_OFFLINE.md. '
    'Uygulama kendiliğinden paket kurmaz veya indirmez.'
)


class LocalDependencyError(ImportError):
    """A missing local package or incompatible binary bundle."""


def runtime_identity():
    machine = platform.machine().lower()
    if machine == 'x86_64':
        machine = 'amd64'
    return {
        'implementation': sys.implementation.name,
        'python': list(sys.version_info[:2]),
        'platform': sys.platform,
        'machine': machine,
        'bits': struct.calcsize('P') * 8,
    }


def activate_local_dependencies(libs_dir=None):
    """Prepend libs and refuse to silently use system-installed dependencies."""
    folder = Path(libs_dir).resolve() if libs_dir is not None else LIBS
    if not folder.is_dir():
        raise LocalDependencyError('Yerel bağımlılık klasörü bulunamadı: libs.\n\n' + PREPARATION_HINT)
    manifest = folder / 'arar_bundle.json'
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding='utf-8'))
            expected = data['runtime']
            if not isinstance(expected, dict) or set(expected) != set(runtime_identity()):
                raise ValueError('Geçersiz çalışma ortamı bilgisi')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise LocalDependencyError('libs/arar_bundle.json okunamadı.\n\n' + PREPARATION_HINT) from exc
        if expected != runtime_identity():
            version = '.'.join(map(str, expected['python']))
            raise LocalDependencyError(
                f'Yerel paketler bu Python ile uyumlu değil. Hazırlanan ortam: '
                f'{expected["implementation"]} {version}, {expected["platform"]}, '
                f'{expected["machine"]}, {expected["bits"]} bit.\n\n' + PREPARATION_HINT)
    path = str(folder)
    # Repeated activation stays idempotent and keeps the project bundle first.
    sys.path[:] = [entry for entry in sys.path if entry != path]
    sys.path.insert(0, path)
    importlib.invalidate_caches()
    missing = []
    for name in MODULES:
        spec = importlib.util.find_spec(name)
        if spec is None or not spec.origin or not Path(spec.origin).resolve().is_relative_to(folder):
            missing.append(name)
    if missing:
        raise LocalDependencyError(
            'libs içinde gerekli yerel Python bileşenleri eksik: ' + ', '.join(missing) +
            '. Sistem paketleri yerine proje paketleri kullanılmalıdır.\n\n' + PREPARATION_HINT)
