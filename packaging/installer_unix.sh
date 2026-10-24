#!/bin/sh
set -eu
if [ "$(uname -s)" != Linux ]; then
    printf '%s\n' 'Bu paket Ubuntu/Debian Linux içindir; bu Unix sistemi için ayrı paket gerekir.' >&2
    exit 1
fi
if [ "$(uname -m)" != x86_64 ]; then
    printf '%s\n' 'Bu paket 64 bit Intel/AMD (x86_64) sistemler içindir.' >&2
    exit 1
fi
minimum='@ARAR_MIN_GLIBC@'
libc=$(getconf GNU_LIBC_VERSION 2>/dev/null || true)
case "$libc" in
    'glibc '*) version=${libc#glibc } ;;
    *) printf '%s\n' 'Bu paket glibc tabanlı Ubuntu/Debian sistemler içindir.' >&2; exit 1 ;;
esac
if ! awk -v actual="$version" -v minimum="$minimum" 'BEGIN {
    split(actual,a,"."); split(minimum,b,".");
    exit !((a[1]+0 > b[1]+0) || (a[1]+0 == b[1]+0 && a[2]+0 >= b[2]+0))
}'; then
    printf '%s\n' "glibc $minimum veya üzeri gerekli; bulunan sürüm: $version" >&2
    exit 1
fi
if [ "${1:-}" = --extract ]; then
    [ "$#" = 2 ] || { printf '%s\n' 'Kullanım: sh Arar-Setup.run --extract BOŞ_KLASÖR' >&2; exit 1; }
    mkdir -p -- "$2"
    [ -z "$(ls -A -- "$2")" ] || { printf '%s\n' 'Çıkarma klasörü boş olmalıdır.' >&2; exit 1; }
    destination=$(CDPATH= cd -- "$2" && pwd)
    first=$(awk '/^__ARAR_ARCHIVE_BELOW__$/ {print NR+1; exit}' "$0")
    tail -n +"$first" "$0" | tar -xz -C "$destination"
    printf '%s\n' "Paket çıkarıldı: $destination"
    exit 0
fi
scratch=$(mktemp -d "${TMPDIR:-/tmp}/arar-kurulum.XXXXXXXX")
cleanup() { rm -rf -- "$scratch"; }
trap cleanup EXIT HUP INT TERM
first=$(awk '/^__ARAR_ARCHIVE_BELOW__$/ {print NR+1; exit}' "$0")
tail -n +"$first" "$0" | tar -xz -C "$scratch"
export PYTHONHOME="$scratch/runtime"
export PYTHONUTF8=1
export PYTHONNOUSERSITE=1
export LD_LIBRARY_PATH="$scratch/runtime/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export TCL_LIBRARY="$scratch/runtime/tcl/tcl8.6"
export TK_LIBRARY="$scratch/runtime/tcl/tk8.6"
"$scratch/runtime/bin/python3" -S -B "$scratch/runtime_driver.py" install "$@"
exit 0
__ARAR_ARCHIVE_BELOW__
