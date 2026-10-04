"""Network denial at application entry and local filesystem validation."""
from pathlib import Path
import os
import socket
import ctypes


def install_network_guard():
    def denied(*args, **kwargs):
        raise PermissionError('Arar çevrimdışı çalışır. Ağ bağlantısı engellendi.')

    class OfflineSocket(socket.socket):
        def __init__(self, *args, **kwargs):
            denied()

    socket.socket = OfflineSocket
    socket.SocketType = OfflineSocket
    for name in ('create_connection', 'create_server', 'getaddrinfo', 'gethostbyname',
                 'gethostbyname_ex', 'gethostbyaddr','getnameinfo'):
        setattr(socket, name, denied)


def local_path(value, *, must_exist=False):
    raw = str(value)
    if raw.startswith(('\\\\', '//')) or '://' in raw:
        raise ValueError('Yalnızca bu bilgisayardaki yerel dosya ve klasörler kullanılabilir.')
    candidate = Path(raw).expanduser().absolute()
    _local_drive(candidate)
    # Inspect links before resolving: a junction must not cause the resolver
    # itself to visit a network share. Readlink reads local reparse metadata.
    if os.name == 'nt':
        prefix=Path(candidate.anchor)
        for part in candidate.parts[1:]:
            prefix=prefix/part
            try:
                target=os.readlink(prefix)
            except (OSError,ValueError):
                continue
            if target.startswith('\\\\?\\UNC\\'):
                raise ValueError('Bağlantının hedefi bir ağ konumu. Yerel bir konum seçin.')
            if target.startswith('\\\\?\\'):
                target=target[4:]
            linked=Path(target) if Path(target).is_absolute() else prefix.parent/target
            _local_drive(linked)
    path = candidate.resolve(strict=must_exist)
    if str(path).startswith(('\\\\', '//')):
        raise ValueError('Ağ konumları desteklenmez.')
    _local_drive(path)
    return path


def _local_drive(path):
    if str(path).startswith(('\\\\','//')):
        raise ValueError('Ağ konumları desteklenmez.')
    if os.name == 'nt' and ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor)) == 4:
        raise ValueError('Ağ sürücüleri desteklenmez. Yerel bir konum seçin.')
