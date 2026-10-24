"""Persistent local scan queue. No device, network or third-party service access."""
from contextlib import closing
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import time
import threading
import uuid

from .detection import analyze_page, list_pages
from .exporter import export_groups, safe_filename
from .models import DocumentContext, Evidence, PageResult, ROOT, build_groups
from .offline import local_path


def encode_pages(pages):
    return json.dumps([asdict(page) for page in pages],ensure_ascii=False)


def decode_pages(value):
    pages=[]
    for item in json.loads(value):
        item['evidence']=[Evidence(**entry) for entry in item.get('evidence',[])]
        if item.get('source_signature'):
            item['source_signature']=tuple(item['source_signature'])
        pages.append(PageResult(**item))
    return pages


class ScanStore:
    def __init__(self,folder=None):
        self.folder=local_path(folder or ROOT/'.arar'/'scans')
        self.database=self.folder/'queue.sqlite3'

    def connect(self):
        self.folder.mkdir(parents=True,exist_ok=True)
        connection=sqlite3.connect(self.database,timeout=10)
        connection.row_factory=sqlite3.Row
        connection.execute('''CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL,
            original TEXT NOT NULL, label TEXT NOT NULL, snapshot TEXT NOT NULL,
            status TEXT NOT NULL, pages TEXT NOT NULL DEFAULT '[]',
            error TEXT NOT NULL DEFAULT '', archive TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL)''')
        connection.commit()
        return connection

    def jobs(self,*,pending_only=False,include_pages=True):
        if not self.database.exists():
            return []
        with closing(self.connect()) as db:
            columns='*' if include_pages else 'id,fingerprint,original,label,snapshot,status,error,archive,created'
            condition=" WHERE status NOT IN ('done','dismissed')" if pending_only else ''
            return [dict(row) for row in db.execute('SELECT '+columns+' FROM jobs'+condition+' ORDER BY created,id')]

    def get(self,job_id):
        if not self.database.exists():
            return None
        with closing(self.connect()) as db:
            row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            return dict(row) if row else None

    def fingerprints(self):
        if not self.database.exists():
            return set()
        with closing(self.connect()) as db:
            return {row[0] for row in db.execute('SELECT fingerprint FROM jobs')}

    def migrate_input_labels(self,settings):
        labels={local_path(value):f'Tarama_{index}' for index,value in enumerate(settings.input_dirs,1)}
        for job in self.jobs(pending_only=True,include_pages=False):
            if job['label'] not in ('Canon','Kodak'):
                continue
            fallback='Tarama_1' if job['label']=='Canon' else 'Tarama_2'
            label=labels.get(local_path(job['original']).parent,fallback)
            with closing(self.connect()) as db,db:
                db.execute('UPDATE jobs SET label=? WHERE id=?',(label,job['id']))

    def update(self,job_id,**fields):
        if not fields or not set(fields)<= {'status','pages','error','archive'}:
            raise ValueError('Geçersiz işlem güncellemesi.')
        with closing(self.connect()) as db,db:
            db.execute('UPDATE jobs SET '+','.join(name+'=?' for name in fields)+' WHERE id=?',
                       [*fields.values(),job_id])

    def transition(self,job_id,expected,status,**fields):
        if not set(fields)<={'pages','error','archive'}:
            raise ValueError('Geçersiz işlem güncellemesi.')
        fields={'status':status,**fields}
        with closing(self.connect()) as db,db:
            result=db.execute('UPDATE jobs SET '+','.join(name+'=?' for name in fields)+
                ' WHERE id=? AND status IN ('+','.join('?' for _ in expected)+')',
                [*fields.values(),job_id,*expected])
            return result.rowcount==1

    def dismiss(self,job_ids):
        removed=[]
        for job_id in job_ids:
            job=self.get(job_id)
            if job and self.transition(job_id,('queued','analyzing','review','error'),'dismissed'):
                removed.append(job_id)
                if job['status']!='analyzing':
                    self.cleanup_snapshot(job)
        return removed

    def enqueue(self,source,label,signature):
        source=local_path(source,must_exist=True)
        fingerprint=hashlib.sha256((str(source)+'|'+str(signature)).encode('utf-8')).hexdigest()
        with closing(self.connect()) as db:
            if db.execute('SELECT 1 FROM jobs WHERE fingerprint=?',(fingerprint,)).fetchone():
                return None
        job_id=uuid.uuid4().hex
        directory=self.folder/job_id
        directory.mkdir()
        target=directory/source.name
        try:
            # Keep review independent of the scanner reusing its output filename.
            with source.open('rb') as incoming,target.open('xb') as outgoing:
                shutil.copyfileobj(incoming,outgoing)
            stat=source.stat()
            if (stat.st_size,stat.st_mtime_ns)!=signature:
                raise ValueError('Tarama dosyası hâlâ değişiyor.')
            with target.open('rb') as handle:
                handle.seek(max(0,target.stat().st_size-4096))
                if b'%%EOF' not in handle.read():
                    raise ValueError('PDF yazımı tamamlanmadı.')
            pages=list_pages(target)
            if not pages:
                raise ValueError('PDF içinde sayfa yok.')
            with closing(self.connect()) as db,db:
                db.execute('INSERT INTO jobs(id,fingerprint,original,label,snapshot,status,pages,created) '
                           'VALUES(?,?,?,?,?,?,?,?)',
                           (job_id,fingerprint,str(source),label,str(target),'queued',encode_pages(pages),
                            datetime.now().astimezone().isoformat()))
            return job_id
        except Exception:
            target.unlink(missing_ok=True)
            directory.rmdir()
            raise

    def recover(self):
        for job in self.jobs(include_pages=False):
            if job['status']=='analyzing':
                self.update(job['id'],status='queued')
            elif job['status']=='exporting':
                if archive_committed(job['archive'],job['id']):
                    self.finish(job)
                else:
                    self.update(job['id'],status='review',
                                error='Önceki kayıt tamamlanmadı. Kontrol edip yeniden onaylayın.')
            elif job['status']=='done':
                self.finish(job)
            elif job['status']=='dismissed':
                self.cleanup_snapshot(job)

    def finish(self,job):
        if job['status']!='done':
            self.update(job['id'],status='done',error='')
        self.cleanup_snapshot(job)

    def cleanup_snapshot(self,job):
        # Only our own working copy is disposable; the scanner's source stays.
        try:
            snapshot=local_path(job['snapshot'])
            owned=local_path(self.folder/job['id'])
            if owned.parent==self.folder and snapshot.parent==owned:
                snapshot.unlink(missing_ok=True)
                owned.rmdir()
        except OSError:
            pass  # A preview may still hold it open; retry on next startup.


class FolderWatcher:
    def __init__(self,store,stable_seconds=3):
        self.store=store
        self.stable_seconds=stable_seconds
        self.observed={}

    def poll(self,settings,now=None):
        now=time.monotonic() if now is None else now
        if not settings.auto_watch:
            self.observed.clear()
            return [],[]
        settings.validate_scan_paths()
        known=self.store.fingerprints()
        found=[]
        errors=[]
        present=set()
        for index,value in enumerate(settings.input_dirs,1):
            label=f'Tarama_{index}'
            try:
                folder=local_path(value,must_exist=True)
                for entry in sorted(folder.iterdir()):
                    key=None
                    if entry.suffix.lower()!='.pdf':
                        continue
                    try:
                        source=local_path(entry,must_exist=True)
                        if not source.is_file():
                            continue
                        stat=source.stat()
                        signature=(stat.st_size,stat.st_mtime_ns)
                        key=str(source)
                        present.add(key)
                        fingerprint=hashlib.sha256((key+'|'+str(signature)).encode('utf-8')).hexdigest()
                        if fingerprint in known:
                            continue
                        previous=self.observed.get(key)
                        if previous is None or previous[0]!=signature:
                            self.observed[key]=(signature,now)
                            continue
                        if now-previous[1]<self.stable_seconds or not stat.st_size:
                            continue
                        job_id=self.store.enqueue(source,label,signature)
                        if job_id:
                            found.append(job_id)
                            known.add(fingerprint)
                    except (OSError,ValueError) as exc:
                        if key in self.observed:
                            self.observed[key]=(self.observed[key][0],now)
                        errors.append(entry.name+': '+str(exc))
            except (OSError,ValueError) as exc:
                errors.append(label+': '+str(exc))
        self.observed={key:value for key,value in self.observed.items() if key in present}
        return found,errors


class ScanWorker:
    """Background ingestion/analysis never replaces the UI's review workspace."""
    def __init__(self,store,events,settings):
        self.store,self.events,self.settings=store,events,settings
        self.stop=threading.Event()
        self.watcher=FolderWatcher(store)
        self.thread=None

    def start(self):
        if self.thread is None:
            self.thread=threading.Thread(target=self.run,daemon=True)
            self.thread.start()

    def run(self):
        while not self.stop.is_set():
            settings=self.settings
            try:
                found,errors=self.watcher.poll(settings)
                if found:
                    self.events.put(('scan_queue',))
                self.events.put(('watch_status',errors[0] if errors else ''))
                if settings.auto_watch:
                    job=next((job for job in self.store.jobs(pending_only=True,include_pages=False)
                              if job['status']=='queued'),None)
                    if job:
                        self.analyze(self.store.get(job['id']),settings)
                        continue
            except Exception as exc:
                self.events.put(('watch_status',str(exc)))
            self.stop.wait(1)

    def analyze(self,job,settings):
        if not self.store.transition(job['id'],('queued',),'analyzing',error=''):
            return
        self.events.put(('scan_queue',))
        pages=decode_pages(job['pages'])
        context=DocumentContext()
        try:
            for page in pages:
                if self.interrupted(job):
                    return
                analyze_page(page,self.stop,stamp_threshold=settings.stamp_threshold/100,
                             scan_stamp_threshold=settings.scan_stamp_threshold/100,
                             review_other_barcodes=settings.review_other_barcodes,
                             review_missing_stamp=settings.review_missing_stamp,
                             faint_blue_as_blue=settings.faint_blue_as_blue)
                if self.interrupted(job):
                    return
                context.apply(page,settings)
                context.record(page)
                if page.first_page_error:
                    break
            if self.interrupted(job):
                return
            groups,unassigned=build_groups(pages,settings.grouping)
            if settings.auto_save_scans and groups and not unassigned and not any(page.first_page_error for page in pages):
                self.auto_archive(job,pages,groups,settings)
                return
            if not self.store.transition(job['id'],('analyzing',),'review',pages=encode_pages(pages)):
                self.interrupted(job)
                return
        except Exception as exc:
            if not self.store.transition(job['id'],('analyzing',),'error',pages=encode_pages(pages),error=str(exc)):
                self.interrupted(job)
                return
        self.events.put(('scan_ready',job['id']))

    def interrupted(self,job):
        current=self.store.get(job['id'])
        if current and current['status']=='dismissed':
            self.store.cleanup_snapshot(current)
            return True
        if self.stop.is_set():
            self.store.transition(job['id'],('analyzing',),'queued')
            return True
        return not current or current['status']!='analyzing'

    def auto_archive(self,job,pages,groups,settings):
        if not self.store.transition(job['id'],('analyzing',),'exporting',pages=encode_pages(pages)):
            self.interrupted(job)
            return
        self.events.put(('scan_queue',))
        folder=None
        try:
            settings.validate_scan_paths()
            folder=reserve_archive(settings.archive_dir,job['label'])
            self.store.update(job['id'],archive=str(folder))
            paths=write_archive(groups,folder,job['id'],job['original'],automatic=True)
            self.store.finish(job)
            self.events.put(('scan_saved',job['id'],str(folder),len(groups)))
        except Exception as exc:
            if folder and archive_committed(folder,job['id']):
                self.events.put(('scan_saved',job['id'],str(folder),len(groups)))
                return
            self.store.transition(job['id'],('exporting',),'review',error='Otomatik kayıt başarısız: '+str(exc))
            self.events.put(('scan_ready',job['id']))


def reserve_archive(root,label,now=None):
    now=now or datetime.now().astimezone()
    date=local_path(root)/now.strftime('%Y-%m-%d')
    date.mkdir(parents=True,exist_ok=True)
    for index in range(1,1_000_000):
        folder=date/(now.strftime('%H-%M-%S')+'_'+safe_filename(label)+f'_{index:03d}')
        try:
            folder.mkdir()
            return folder
        except FileExistsError:
            continue
    raise ValueError('Arşiv işlem klasörü oluşturulamadı.')


def write_archive(groups,folder,job_id,original='',*,automatic=False):
    folder=local_path(folder,must_exist=True)
    created=[]
    marker=folder/'Arar_onay.json'
    temporary=folder/'Arar_onay.tmp'
    try:
        created=export_groups(groups,folder)
        temporary.write_text(json.dumps({'islem':job_id,'kaynak':original,
            'kayit_turu':'otomatik' if automatic else 'kullanıcı onayı',
            'onay_zamani':datetime.now().astimezone().isoformat(),
            'dosyalar':[{'ad':path.name,'boyut':path.stat().st_size} for path in created]},
            ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(marker)
        return created
    except Exception:
        temporary.unlink(missing_ok=True)
        for path in created:
            path.unlink(missing_ok=True)
        raise


def archive_committed(folder,job_id):
    try:
        folder=local_path(folder,must_exist=True)
        data=json.loads((folder/'Arar_onay.json').read_text(encoding='utf-8'))
        return data['islem']==job_id and bool(data['dosyalar']) and all(
            Path(item['ad']).name==item['ad'] and
            (folder/item['ad']).stat().st_size==item['boyut'] for item in data['dosyalar'])
    except (OSError,ValueError,KeyError,TypeError):
        return False
