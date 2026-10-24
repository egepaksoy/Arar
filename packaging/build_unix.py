"""Build a self-contained Ubuntu/Debian x86_64 .run package from local wheels."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parent.parent


def environment(prefix):
    return {**os.environ,'PYTHONHOME':str(prefix/'runtime'),'PYTHONUTF8':'1','PYTHONNOUSERSITE':'1',
            'LD_LIBRARY_PATH':str(prefix/'runtime/lib'),
            'TCL_LIBRARY':str(prefix/'runtime/tcl/tcl8.6'),'TK_LIBRARY':str(prefix/'runtime/tcl/tk8.6')}


def validate(prefix):
    subprocess.run([str(prefix/'runtime/bin/python3'),'-S','-B',str(prefix/'runtime_driver.py'),'verify'],
                   env=environment(prefix),check=True,cwd=prefix)


def shared_libraries(stage):
    library_dir=stage/'runtime/lib'
    objects=[stage/'runtime/bin/python3']+[path for path in stage.rglob('*') if path.is_file() and '.so' in path.name]
    libraries={}
    core=re.compile(r'^(libc\.so|libm\.so|libpthread\.so|libdl\.so|librt\.so|libresolv\.so|libnss_|ld-linux)')
    for binary in objects:
        result=subprocess.run(['ldd',str(binary)],capture_output=True,text=True)
        if 'not found' in result.stdout:
            raise RuntimeError('Paylaşılan kütüphane eksik: '+str(binary)+'\n'+result.stdout)
        for line in result.stdout.splitlines():
            match=re.search(r'=>\s+(/\S+)',line)
            if not match:
                continue
            path=Path(match[1])
            if path.resolve().is_relative_to(stage) or core.match(path.name):
                continue
            libraries[path.name]=path
    for name,path in libraries.items():
        shutil.copy2(path,library_dir/name)
    # Debian/Ubuntu copyright files accompany copied system shared libraries.
    licenses=stage/'runtime/licenses'
    licenses.mkdir()
    for path in [Path(sys.executable),*libraries.values()]:
        result=subprocess.run(['dpkg-query','-S',str(path)],capture_output=True,text=True)
        for line in result.stdout.splitlines():
            package=line.split(': ',1)[0]
            notice=Path('/usr/share/doc')/package.split(':')[0]/'copyright'
            if notice.is_file():
                shutil.copy2(notice,licenses/(package.replace(':','_')+'.txt'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheelhouse',type=Path,required=True)
    parser.add_argument('--version',default='2026.10.24.2')
    args=parser.parse_args()
    if sys.platform!='linux' or platform.machine().lower()!='x86_64' or sys.version_info<(3,11):
        parser.error('Bu derleme Ubuntu/Debian x86_64 üzerinde CPython 3.11+ ile yapılmalıdır.')
    if not args.wheelhouse.is_dir():
        parser.error('Hedef Python için Linux wheel dosyalarını içeren yerel klasör gerekli.')
    import tkinter as tk
    root=tk.Tk()
    root.withdraw()
    tcl=Path(root.tk.eval('info library'))
    tk_library=Path(root.tk.eval('set tk_library'))
    root.destroy()
    dist=ROOT/'dist'
    dist.mkdir(exist_ok=True)
    # Native Linux temp storage avoids slow per-file I/O on a mounted NTFS tree.
    with tempfile.TemporaryDirectory(prefix='arar-linux-offline-') as scratch:
        scratch=Path(scratch)
        stage=scratch/'payload'
        app=stage/'app'
        app.mkdir(parents=True)
        ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pyo')
        for name in ('arar','assets'):
            shutil.copytree(ROOT/name,app/name,ignore=ignore)
        for name in ('main.py','local_dependencies.py','README.md','README_OFFLINE.md'):
            shutil.copy2(ROOT/name,app/name)
        subprocess.run([sys.executable,'-m','pip','install','--no-index','--only-binary=:all:',
                        '--no-compile','--find-links',str(args.wheelhouse.resolve()),'--target',str(app/'libs'),
                        '-r',str(ROOT/'requirements.txt')],check=True)
        machine=platform.machine().lower().replace('x86_64','amd64')
        identity={'implementation':sys.implementation.name,'python':list(sys.version_info[:2]),
                  'platform':sys.platform,'machine':machine,'bits':64}
        (app/'libs/arar_bundle.json').write_text(json.dumps({'runtime':identity},indent=2),encoding='utf-8')
        runtime=stage/'runtime'
        (runtime/'bin').mkdir(parents=True)
        (runtime/'lib').mkdir()
        shutil.copy2(Path(sys.executable).resolve(),runtime/'bin/python3')
        shutil.copytree(sysconfig.get_path('stdlib'),runtime/'lib'/f'python{sys.version_info.major}.{sys.version_info.minor}',
                        ignore=shutil.ignore_patterns('dist-packages','site-packages','__pycache__','*.pyc','test','tests','idlelib','ensurepip'))
        shutil.copytree(tcl,runtime/'tcl/tcl8.6',ignore=ignore)
        shutil.copytree(tk_library,runtime/'tcl/tk8.6',ignore=ignore)
        shutil.copy2(ROOT/'packaging/runtime_driver.py',stage/'runtime_driver.py')
        shared_libraries(stage)
        print('Linux çalışma ortamı hazır; doğrulama başlıyor.',flush=True)
        validate(stage)
        files=sorted(path.relative_to(stage).as_posix() for path in stage.rglob('*') if path.is_file())
        version=platform.libc_ver()[1]
        metadata={'product':'Arar','version':args.version,'platform':'Linux x86_64',
                  'minimum_glibc':version,'python':platform.python_version(),'files':files}
        (stage/'installed_files.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        archive=scratch/'payload.tar.gz'
        with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
            for path in sorted(stage.rglob('*')):
                if path.is_file():
                    info=tar.gettarinfo(str(path),arcname=path.relative_to(stage).as_posix())
                    info.uid=info.gid=0
                    info.uname=info.gname=''
                    info.mode=0o755 if path==runtime/'bin/python3' else 0o644
                    with path.open('rb') as handle:
                        tar.addfile(info,handle)
        output=dist/f'Arar-Setup-{args.version}-linux-x86_64-glibc{version}.run'
        with output.open('wb') as destination:
            header=(ROOT/'packaging/installer_unix.sh').read_text(encoding='utf-8').replace('@ARAR_MIN_GLIBC@',version)
            destination.write(header.encode('utf-8'))
            destination.write(archive.read_bytes())
        output.chmod(0o755)
        print('Kurulum paketi oluşturuldu; kurulum/güncelleme/kaldırma sınanıyor.',flush=True)
        extracted=scratch/'extracted'
        subprocess.run(['sh',str(output),'--extract',str(extracted)],check=True)
        validate(extracted)
        installed=scratch/'kurulum-çğıöşü'
        subprocess.run(['sh',str(output),'--prefix',str(installed),'--no-shortcuts'],check=True)
        validate(installed)
        # Reinstall preserves settings and documents, including Turkish paths.
        (installed/'app/.arar').mkdir()
        keep=installed/'app/.arar/korunan-çğıöşü.txt'
        keep.write_text('İşlem sırası ve belgeler',encoding='utf-8')
        subprocess.run(['sh',str(output),'--prefix',str(installed),'--no-shortcuts'],check=True)
        assert keep.read_text(encoding='utf-8')=='İşlem sırası ve belgeler'
        subprocess.run(['sh',str(installed/'kaldir.sh')],check=True)
        assert keep.exists()
        assert not (installed/'runtime/bin/python3').exists()
        digest=hashlib.sha256(output.read_bytes()).hexdigest()
        (dist/(output.name+'.sha256')).write_text(digest+'  '+output.name+'\n',encoding='ascii')
        print(str(output))
        print(f'{output.stat().st_size/1024/1024:.1f} MiB | SHA256 {digest}')


if __name__=='__main__':
    main()
