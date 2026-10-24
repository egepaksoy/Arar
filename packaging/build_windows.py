"""Build an offline Windows x64 installer from an existing local CPython runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parent.parent


def copy_tree(source,target):
    shutil.copytree(source,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pyo'),dirs_exist_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python-home',type=Path,default=Path(sys.base_prefix))
    parser.add_argument('--version',default='2026.10.24.1')
    args=parser.parse_args()
    if os.name!='nt' or sys.maxsize<=2**32:
        parser.error('Build requires Windows x64 and a matching local CPython runtime.')
    runtime=args.python_home.resolve()
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.is_file():
        parser.error('The local .NET Framework C# compiler was not found.')
    build=ROOT/'build'
    dist=ROOT/'dist'
    build.mkdir(exist_ok=True)
    dist.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='offline-',dir=build) as scratch:
        stage=Path(scratch)/'payload'
        app=stage/'app'
        app.mkdir(parents=True)
        for name in ('arar','assets','libs'):
            copy_tree(ROOT/name,app/name)
        for name in ('main.py','local_dependencies.py','README.md','README_OFFLINE.md'):
            shutil.copy2(ROOT/name,app/name)
        bundled=stage/'runtime'
        bundled.mkdir()
        for name in ('python.exe','pythonw.exe','python3.dll','python312.dll','vcruntime140.dll',
                     'vcruntime140_1.dll','LICENSE.txt'):
            shutil.copy2(runtime/name,bundled/name)
        # Copy standard library and Tcl/Tk only, never development site-packages.
        shutil.copytree(runtime/'Lib',bundled/'Lib',ignore=shutil.ignore_patterns(
            'site-packages','__pycache__','*.pyc','test','tests','idlelib','ensurepip'))
        for name in ('DLLs','tcl'):
            copy_tree(runtime/name,bundled/name)
        # Windows PowerShell 5.1 needs a BOM to decode Turkish UTF-8 scripts.
        (stage/'uninstall.ps1').write_text((ROOT/'packaging/uninstall.ps1').read_text(encoding='utf-8-sig'),encoding='utf-8-sig')
        shutil.copy2(ROOT/'packaging/INSTALLATION.txt',stage/'KURULUM.txt')
        (stage/'uninstall.cmd').write_text('@echo off\r\nchcp 65001 >nul\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"\r\n',encoding='ascii',newline='')
        assert (stage/'uninstall.ps1').read_bytes().startswith(b'\xef\xbb\xbf')
        # Exercise Windows PowerShell 5.1 with a Turkish fake profile. Real
        # shortcuts/registry entries are protected by their installation path.
        profile=Path(scratch)/'Türkçe-çğıöşü'
        fake_install=profile/'Programs/Arar'
        (fake_install/'app/.arar').mkdir(parents=True)
        owned=fake_install/'app/uygulama-çğıöşü.txt'
        owned.write_text('kurulum dosyası',encoding='utf-8')
        kept=fake_install/'app/.arar/ayarlar-çğıöşü.json'
        kept.write_text('{}',encoding='utf-8')
        shutil.copy2(stage/'uninstall.ps1',fake_install/'uninstall.ps1')
        (fake_install/'installed_files.json').write_text(json.dumps(
            {'product':'Arar','files':['app/uygulama-çğıöşü.txt']},ensure_ascii=False),encoding='utf-8')
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                               '-File',str(fake_install/'uninstall.ps1'),'-NoPause'],
                              env={**os.environ,'LOCALAPPDATA':str(profile)},capture_output=True,encoding='utf-8',check=True)
        assert 'Arar kaldırıldı' in result.stdout and 'çğıöşü' in result.stdout
        assert not owned.exists() and kept.exists()
        print('turkish_uninstaller_ok')
        # Validate the actual copied runtime, including its native GUI/PDF DLLs.
        verification='''from local_dependencies import activate_local_dependencies
activate_local_dependencies()
from arar.offline import install_network_guard
install_network_guard()
import tkinter as tk, sqlite3, tempfile
from pathlib import Path
from pypdf import PdfWriter
from arar.detection import list_pages, render_page
from arar.app import ArarApp
root=tk.Tk(); root.withdraw(); root.update(); root.destroy()
with tempfile.TemporaryDirectory() as folder:
    source=Path(folder)/'check.pdf'
    writer=PdfWriter(); writer.add_blank_page(width=100,height=100)
    with source.open('wb') as handle: writer.write(handle)
    assert len(list_pages(source))==1
    assert render_page(source,0)[0].width>0
with sqlite3.connect(':memory:') as db: db.execute('SELECT 1')
print('bundled_runtime_ok')
'''
        subprocess.run([str(bundled/'python.exe'),'-S','-B','-c',verification],cwd=app,check=True)
        files=sorted(path.relative_to(stage).as_posix() for path in stage.rglob('*') if path.is_file())
        metadata={'product':'Arar','version':args.version,'platform':'Windows x64','files':files}
        (stage/'installed_files.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        payload=Path(scratch)/'payload.zip'
        with zipfile.ZipFile(payload,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for path in sorted(stage.rglob('*')):
                if path.is_file():
                    archive.write(path,path.relative_to(stage).as_posix())
        executable=dist/f'Arar-Setup-{args.version}-win-x64.exe'
        subprocess.run([str(compiler),'/nologo','/target:winexe','/platform:x64','/optimize+',
                        '/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll',
                        '/reference:System.IO.Compression.dll','/reference:System.IO.Compression.FileSystem.dll',
                        '/reference:System.Web.Extensions.dll',
                        '/resource:'+str(payload)+',Arar.Payload','/out:'+str(executable),
                        str(ROOT/'packaging/Setup.cs')],check=True)
        # Exercise the single-file installer payload independently of the staging tree.
        extracted=Path(scratch)/'extracted'
        subprocess.run([str(executable),'--extract',str(extracted)],check=True)
        expected=json.loads((extracted/'installed_files.json').read_text(encoding='utf-8'))
        assert expected['version']==args.version
        assert not (extracted/'app/.arar').exists()
        subprocess.run([str(extracted/'runtime/python.exe'),'-S','-B','-c',verification],
                       cwd=extracted/'app',check=True)
        digest=hashlib.sha256(executable.read_bytes()).hexdigest()
        (dist/(executable.name+'.sha256')).write_text(digest+'  '+executable.name+'\n',encoding='ascii')
        print(str(executable))
        print(f'{executable.stat().st_size/1024/1024:.1f} MiB | SHA256 {digest}')


if __name__=='__main__':
    main()
