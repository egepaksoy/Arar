"""Local install, launch, verification and uninstall for a bundled Linux runtime."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

PACKAGE=Path(__file__).resolve().parent


def locked(prefix):
    prefix.mkdir(parents=True,exist_ok=True)
    handle=(prefix/'run.lock').open('a')
    try:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise RuntimeError('Arar çalışıyor. Pencereyi kapatıp yeniden deneyin.') from None
    return handle


def verify(prefix):
    sys.path.insert(0,str(prefix/'app'))
    from local_dependencies import activate_local_dependencies
    activate_local_dependencies(prefix/'app/libs')
    from arar.offline import install_network_guard
    install_network_guard()
    import sqlite3
    import tempfile
    import tkinter as tk
    from pypdf import PdfWriter
    from arar.detection import list_pages,render_page,analyze_page
    from arar.app import ArarApp
    from arar.report_ocr import find_report_headings
    from PIL import Image
    assert find_report_headings(Image.open(prefix/'app/assets/receiving_report.png'))[1]
    assert Path(sys.prefix).resolve()==(prefix/'runtime').resolve()
    assert Path(os.__file__).resolve().is_relative_to(prefix/'runtime')
    root=tk.Tk()
    root.withdraw()
    assert Path(root.tk.eval('info library')).resolve().is_relative_to(prefix/'runtime')
    app=ArarApp(root)
    root.update()
    app.close()
    with tempfile.TemporaryDirectory() as scratch:
        source=Path(scratch)/'doğrulama.pdf'
        writer=PdfWriter()
        writer.add_blank_page(width=100,height=100)
        with source.open('wb') as handle:
            writer.write(handle)
        assert len(list_pages(source))==1
        assert render_page(source,0)[0].width>0
        scan=Path(scratch)/'ocr-scan.pdf'
        Image.open(prefix/'app/assets/receiving_report.png').convert('RGB').save(scan,'PDF',resolution=288)
        result=analyze_page(list_pages(scan)[0])
        assert result.barcode=='THAEK12026124'
        assert any(e.kind=='heading' for e in result.evidence)
    with sqlite3.connect(':memory:') as db:
        assert db.execute('SELECT 1').fetchone()==(1,)
    print('Paket doğrulandı: Python, Tkinter, SQLite, PDF ve ağ engeli çalışıyor.')


def launcher(prefix,command):
    import shlex
    root=shlex.quote(str(prefix))
    return ('#!/bin/sh\nset -eu\nARAR_ROOT='+root+'\n'
        'export PYTHONHOME="$ARAR_ROOT/runtime"\nexport PYTHONUTF8=1\nexport PYTHONNOUSERSITE=1\n'
        'export LD_LIBRARY_PATH="$ARAR_ROOT/runtime/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"\n'
        'export TCL_LIBRARY="$ARAR_ROOT/runtime/tcl/tcl8.6"\nexport TK_LIBRARY="$ARAR_ROOT/runtime/tcl/tk8.6"\n'
        'exec "$ARAR_ROOT/runtime/bin/python3" -S -B "$ARAR_ROOT/runtime_driver.py" '+command+' "$@"\n')


def install(prefix,no_shortcuts):
    if prefix==PACKAGE or prefix.is_relative_to(PACKAGE) or PACKAGE.is_relative_to(prefix):
        raise ValueError('Kurulum konumu geçici paket klasöründen ayrı olmalıdır.')
    with locked(prefix):
        previous=prefix/'installation.json'
        if any(prefix.iterdir()) and not previous.exists() and any(p.name!='run.lock' for p in prefix.iterdir()):
            raise ValueError('Bu klasörde başka dosyalar var. Boş bir kurulum klasörü seçin.')
        bin_dir=Path.home()/'.local/bin'
        command=bin_dir/'arar'
        applications=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'applications'
        desktop=applications/'arar.desktop'
        if not no_shortcuts:
            if (command.exists() or command.is_symlink()) and (not command.is_symlink() or command.resolve()!=prefix/'arar.sh'):
                raise ValueError('~/.local/bin/arar zaten başka bir dosya. --no-shortcuts ile kurabilirsiniz.')
            if desktop.exists() and str(prefix) not in desktop.read_text(encoding='utf-8'):
                raise ValueError('arar.desktop zaten başka bir uygulamaya ait. --no-shortcuts ile kurabilirsiniz.')
        old_shortcuts=json.loads(previous.read_text(encoding='utf-8')).get('shortcuts',[]) if previous.exists() else []
        data=json.loads((PACKAGE/'installed_files.json').read_text(encoding='utf-8'))
        for relative in data['files']+['installed_files.json']:
            target=prefix/relative
            if not target.resolve().is_relative_to(prefix):
                raise ValueError('Geçersiz kurulum yolu.')
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(PACKAGE/relative,target)
        for name,command in (('arar.sh','run'),('kaldir.sh','uninstall')):
            target=prefix/name
            target.write_text(launcher(prefix,command),encoding='utf-8',newline='\n')
            target.chmod(0o755)
        # A partially completed shortcut registration can be retried or removed.
        previous.write_text(json.dumps({'product':'Arar','prefix':str(prefix),'shortcuts':old_shortcuts},ensure_ascii=False),encoding='utf-8')
        shortcuts=[]
        if not no_shortcuts:
            bin_dir.mkdir(parents=True,exist_ok=True)
            command=bin_dir/'arar'
            if not command.is_symlink():
                command.symlink_to(prefix/'arar.sh')
            shortcuts.append(str(command))
            previous.write_text(json.dumps({'product':'Arar','prefix':str(prefix),
                'shortcuts':list(dict.fromkeys(old_shortcuts+shortcuts))},ensure_ascii=False),encoding='utf-8')
            applications.mkdir(parents=True,exist_ok=True)
            escaped=str(prefix/'arar.sh').replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
            desktop.write_text('[Desktop Entry]\nType=Application\nName=Arar\nComment=Çevrimdışı belge ayırma\n'
                               'Exec="'+escaped+'"\nTerminal=false\nCategories=Office;\n',encoding='utf-8')
            shortcuts.append(str(desktop))
        # Keep earlier shortcuts registered when updating with --no-shortcuts.
        shortcuts=list(dict.fromkeys(shortcuts+old_shortcuts))
        previous.write_text(json.dumps({'product':'Arar','prefix':str(prefix),'shortcuts':shortcuts},ensure_ascii=False),encoding='utf-8')
    print('Arar kuruldu: '+str(prefix))
    print('Başlatmak için: '+str(prefix/'arar.sh'))
    print('Kaldırmak için: '+str(prefix/'kaldir.sh'))


def uninstall():
    prefix=PACKAGE
    info=json.loads((prefix/'installation.json').read_text(encoding='utf-8'))
    if info.get('product')!='Arar' or info.get('prefix')!=str(prefix):
        raise ValueError('Arar kurulum kaydı doğrulanamadı.')
    with locked(prefix):
        data=json.loads((prefix/'installed_files.json').read_text(encoding='utf-8'))
        directories=set()
        for relative in data['files']+['installed_files.json','installation.json','arar.sh','kaldir.sh']:
            target=prefix/relative
            if not target.parent.resolve().is_relative_to(prefix):
                raise ValueError('Geçersiz kaldırma yolu.')
            if target.is_file() or target.is_symlink():
                target.unlink()
            directories.update(parent for parent in target.parents if parent.is_relative_to(prefix))
        for value in info.get('shortcuts',[]):
            path=Path(value)
            if path.is_symlink() and path.resolve()==prefix/'arar.sh':
                path.unlink()
            elif path.name=='arar.desktop' and path.is_file() and str(prefix) in path.read_text(encoding='utf-8'):
                path.unlink()
        for folder in sorted(directories,key=lambda p:len(p.parts),reverse=True):
            try:
                folder.rmdir()
            except OSError:
                pass
    (prefix/'run.lock').unlink(missing_ok=True)
    print('Arar kaldırıldı. Ayarlar ve belgeler korundu: '+str(prefix))


def main():
    parser=argparse.ArgumentParser(description='Arar çevrimdışı Linux kurulumu')
    parser.add_argument('command',choices=('install','uninstall','run','verify'))
    parser.add_argument('--prefix',type=Path,default=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'arar')
    parser.add_argument('--no-shortcuts',action='store_true')
    args=parser.parse_args()
    if args.command=='install':
        install(args.prefix.expanduser().resolve(),args.no_shortcuts)
    elif args.command=='uninstall':
        uninstall()
    elif args.command=='verify':
        verify(PACKAGE)
    else:
        with locked(PACKAGE):
            os.chdir(PACKAGE/'app')
            sys.path.insert(0,str(PACKAGE/'app'))
            runpy.run_path(str(PACKAGE/'app/main.py'),run_name='__main__')


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        print('İşlem tamamlanamadı: '+str(exc),file=sys.stderr)
        raise SystemExit(1)
