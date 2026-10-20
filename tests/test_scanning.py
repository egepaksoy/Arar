from datetime import datetime
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch

from local_dependencies import activate_local_dependencies
activate_local_dependencies()
from pypdf import PdfReader, PdfWriter
from arar.models import Settings, build_groups
from arar.scanning import (ScanStore, FolderWatcher, ScanWorker, decode_pages,
                           encode_pages, reserve_archive, write_archive, archive_committed)


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.incoming=self.root/'Canon'
        self.incoming.mkdir()
        self.settings=Settings(auto_watch=True,canon_input_dir=str(self.incoming),
                               archive_dir=str(self.root/'archive'))
        self.store=ScanStore(self.root/'queue')
        self.watcher=FolderWatcher(self.store,stable_seconds=3)
        self.source=self.incoming/'scan.PDF'
        writer=PdfWriter()
        writer.add_blank_page(width=595,height=842)
        writer.add_blank_page(width=595,height=842)
        with self.source.open('wb') as handle:
            writer.write(handle)

    def tearDown(self):
        self.temp.cleanup()

    def enqueue(self):
        stat=self.source.stat()
        return self.store.enqueue(self.source,'Canon',(stat.st_size,stat.st_mtime_ns))

    def test_file_stability_disabled_switch_and_persistent_duplicate_detection(self):
        self.assertEqual(self.watcher.poll(self.settings,now=0)[0],[])
        self.assertEqual(self.watcher.poll(self.settings,now=2)[0],[])
        with self.source.open('ab') as handle:
            handle.write(b'\n% still writing\n')
        self.assertEqual(self.watcher.poll(self.settings,now=3)[0],[])
        self.assertEqual(self.watcher.poll(self.settings,now=5)[0],[])
        added,errors=self.watcher.poll(self.settings,now=6)
        self.assertEqual(len(added),1)
        self.assertFalse(errors)
        restarted=FolderWatcher(ScanStore(self.root/'queue'))
        self.assertEqual(restarted.poll(self.settings,now=100)[0],[])
        self.assertEqual(len(self.store.jobs()),1)
        self.settings.auto_watch=False
        (self.incoming/'new.pdf').write_bytes(self.source.read_bytes())
        restarted.poll(self.settings,now=200)
        restarted.poll(self.settings,now=210)
        self.assertEqual(len(self.store.jobs()),1)

    def test_incomplete_pdf_is_not_queued_and_can_be_completed_later(self):
        complete=self.source.read_bytes()
        self.source.write_bytes(complete[:100])
        self.watcher.poll(self.settings,now=0)
        added,errors=self.watcher.poll(self.settings,now=4)
        self.assertEqual(added,[])
        self.assertTrue(errors)
        self.assertEqual(self.store.jobs(),[])
        self.source.write_bytes(complete)
        self.watcher.poll(self.settings,now=5)
        self.assertEqual(len(self.watcher.poll(self.settings,now=9)[0]),1)

    def test_working_copy_survives_source_overwrite_and_decisions_survive_restart(self):
        job_id=self.enqueue()
        job=self.store.jobs()[0]
        copied=Path(job['snapshot']).read_bytes()
        self.source.write_bytes(b'scanner reused the filename')
        self.assertEqual(Path(job['snapshot']).read_bytes(),copied)
        pages=decode_pages(job['pages'])
        pages[0].decision='cover'
        pages[0].manual_barcode='MANUAL'
        self.store.update(job_id,status='review',pages=encode_pages(pages))
        loaded=decode_pages(ScanStore(self.root/'queue').jobs()[0]['pages'])
        self.assertEqual((loaded[0].effective_state,loaded[0].number),('cover','MANUAL'))
        self.assertIsInstance(loaded[0].source_signature,tuple)

    def test_worker_analyzes_without_archiving_and_stops_on_missing_first_cover_data(self):
        self.enqueue()
        worker=ScanWorker(self.store,queue.Queue(),self.settings)
        def analyzed(page,*args,**kwargs):
            page.state='cover' if page.index==0 else 'attachment'
            page.barcode='REPORT' if page.index==0 else ''
            page.target_found=page.index==0
            page.stamp='blue' if page.index==0 else 'none'
            return page
        with patch('arar.scanning.analyze_page',side_effect=analyzed):
            worker.analyze(self.store.jobs()[0],self.settings)
        job=self.store.jobs()[0]
        self.assertEqual(job['status'],'review')
        self.assertEqual([p.state for p in decode_pages(job['pages'])],['cover','attachment'])
        self.assertFalse(Path(self.settings.archive_dir).exists())
        def missing(page,*args,**kwargs):
            page.state='review'
            page.first_page_error=True
        with patch('arar.scanning.analyze_page',side_effect=missing) as analyze:
            worker.analyze(job,self.settings)
        self.assertEqual(analyze.call_count,1)
        self.assertTrue(decode_pages(self.store.jobs()[0]['pages'])[0].first_page_error)

    def test_date_archive_is_collision_safe_and_export_commit_recovers_after_restart(self):
        job_id=self.enqueue()
        job=self.store.jobs()[0]
        pages=decode_pages(job['pages'])
        pages[0].state='cover'
        pages[0].barcode='REPORT'
        pages[1].state='attachment'
        groups,_=build_groups(pages)
        now=datetime(2026,10,21,14,32,8)
        first=reserve_archive(self.settings.archive_dir,'Canon',now)
        second=reserve_archive(self.settings.archive_dir,'Canon',now)
        self.assertEqual(first.parent.name,'2026-10-21')
        self.assertEqual(first.name,'14-32-08_Canon_001')
        self.assertEqual(second.name,'14-32-08_Canon_002')
        self.store.update(job_id,status='exporting',archive=str(first),pages=encode_pages(pages))
        paths=write_archive(groups,first,job_id,str(self.source))
        self.assertEqual(len(PdfReader(paths[0]).pages),2)
        self.assertTrue(archive_committed(first,job_id))
        self.store.recover()
        self.assertEqual(self.store.jobs()[0]['status'],'done')
        self.assertFalse(Path(job['snapshot']).exists())
        self.assertTrue(self.source.exists())

    def test_unfinished_analysis_or_export_is_recoverable_without_auto_approval(self):
        job_id=self.enqueue()
        self.store.update(job_id,status='analyzing')
        self.store.recover()
        self.assertEqual(self.store.jobs()[0]['status'],'queued')
        self.store.update(job_id,status='exporting',archive=str(self.root/'missing'))
        self.store.recover()
        job=self.store.jobs()[0]
        self.assertEqual(job['status'],'review')
        self.assertTrue(job['error'])
        self.assertFalse(Path(self.settings.archive_dir).exists())

    def test_failed_export_has_no_commit_marker_or_partial_files(self):
        job_id=self.enqueue()
        pages=decode_pages(self.store.jobs()[0]['pages'])
        pages[0].state='cover'
        pages[0].barcode='REPORT'
        pages[1].state='attachment'
        pages[1].index=999
        groups,_=build_groups(pages)
        folder=reserve_archive(self.settings.archive_dir,'Canon')
        with self.assertRaises(IndexError):
            write_archive(groups,folder,job_id)
        self.assertEqual(list(folder.iterdir()),[])
        self.assertFalse(archive_committed(folder,job_id))

    def test_configuration_rejects_network_overlapping_and_missing_inputs(self):
        for fields in ({'canon_input_dir':r'\\server\share'},
                       {'archive_dir':str(self.incoming/'archive')},
                       {'kodak_input_dir':str(self.incoming)},
                       {'canon_input_dir':''}):
            with self.subTest(fields=fields):
                from dataclasses import replace
                with self.assertRaises(ValueError):
                    replace(self.settings,**fields).validate_scan_paths()


if __name__=='__main__':
    unittest.main()
