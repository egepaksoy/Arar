#!/bin/sh
# Prepare packages for this platform; all options go to the shared Python script.
SCRIPT_PARENT=${0%/*}
if [ "$SCRIPT_PARENT" = "$0" ]; then SCRIPT_PARENT=.; fi
SCRIPT_DIR=$(CDPATH= cd -- "$SCRIPT_PARENT" && pwd) || exit 1
cd "$SCRIPT_DIR" || exit 1
export PYTHONUTF8=1

compatible() {
    "$1" -c 'import sys, tkinter; sys.exit(0 if sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 12) else 1)' >/dev/null 2>&1
}

if [ -n "${ARAR_PYTHON:-}" ]; then
    if compatible "$ARAR_PYTHON"; then
        exec "$ARAR_PYTHON" -B "$SCRIPT_DIR/prepare_local_libs.py" "$@"
    fi
    echo "ARAR_PYTHON uyumlu değil. Tkinter içeren CPython 3.12.x gerekli." >&2
    exit 1
fi

for candidate in "$SCRIPT_DIR/.venv/bin/python3" "$SCRIPT_DIR/.venv/bin/python" \
    python3.12 python3 python \
    "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"; do
    if compatible "$candidate"; then
        exec "$candidate" -B "$SCRIPT_DIR/prepare_local_libs.py" "$@"
    fi
done

echo "Tkinter içeren CPython 3.12.x bulunamadı. README_OFFLINE.md dosyasını okuyun." >&2
exit 1
