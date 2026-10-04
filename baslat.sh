#!/bin/sh
set -e

# Betiğin bulunduğu dizine geç
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Proje içi yerel sanal ortam (.venv)
if [ -x ".venv/bin/python3" ]; then
    exec ".venv/bin/python3" "main.py" "$@"
elif [ -x ".venv/bin/python" ]; then
    exec ".venv/bin/python" "main.py" "$@"
fi

# 2. Ortam değişkeni ile belirtilen Python yolu
if [ -n "$ARAR_PYTHON" ] && [ -x "$ARAR_PYTHON" ]; then
    exec "$ARAR_PYTHON" "main.py" "$@"
fi

# 3. Kullanıcı önbelleğindeki runtime (varsa)
CODEX_PYTHON="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
if [ -x "$CODEX_PYTHON" ]; then
    exec "$CODEX_PYTHON" "main.py" "$@"
fi

# 4. Sistem Python 3
if command -v python3 >/dev/null 2>&1; then
    exec python3 "main.py" "$@"
fi

# 5. Sistem 'python' komutu (Python 3 ise)
if command -v python >/dev/null 2>&1; then
    if python -c "import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)" >/dev/null 2>&1; then
        exec python "main.py" "$@"
    fi
fi

echo "Python 3 ve gerekli kütüphaneler bulunamadı." >&2
echo "Lütfen .venv ortamını kurun veya README.md dosyasındaki kurulum adımlarını uygulayın." >&2
exit 1
