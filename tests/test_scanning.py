from datetime import datetime
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch

from local_dependencies import activate_local_dependencies
activate_local_dependencies()
from pypdf import PdfReader, PdfWriter
from arar.models import PageResult, Settings, build_groups
from arar.scanning import (ScanStore, FolderWatcher, ScanWorker, decode_pages,
                           approval_problem, encode_pages, reserve_archive, write_archive, archive_committed)


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.incoming=self.root/'incoming'
        self.incoming.mkdir()
        self.settings=Settings(auto_watch=True,input_dirs=[str(self.incoming)],
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
        return self.store.enqueue(self.source,'Tarama_1',(stat.st_size,stat.st_mtime_ns))

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
        self.store.update(job['id'],status='queued')
        with patch('arar.scanning.analyze_page',side_effect=missing) as analyze:
            worker.analyze(job,self.settings)
        self.assertEqual(analyze.call_count,1)
        self.assertTrue(decode_pages(self.store.jobs()[0]['pages'])[0].first_page_error)

    def analyze_clean(self,page,*args,**kwargs):
        page.state='cover' if page.index==0 else 'attachment'
        page.barcode='REPORT' if page.index==0 else ''
        page.target_found=page.index==0
        page.stamp='blue' if page.index==0 else 'none'
        return page

    def test_auto_save_only_archives_complete_groups_and_records_automatic_mode(self):
        job_id=self.enqueue()
        self.settings.auto_save_scans=True
        events=queue.Queue()
        worker=ScanWorker(self.store,events,self.settings)
        with patch('arar.scanning.analyze_page',side_effect=self.analyze_clean):
            worker.analyze(self.store.get(job_id),self.settings)
        job=self.store.get(job_id)
        self.assertEqual(job['status'],'done')
        self.assertTrue((Path(job['archive'])/'REPORT.pdf').exists())
        import json
        marker=json.loads((Path(job['archive'])/'Arar_onay.json').read_text(encoding='utf-8'))
        self.assertEqual(marker['kayit_turu'],'otomatik')
        self.assertTrue(self.source.exists())
        self.assertIn('scan_saved',[event[0] for event in list(events.queue)])
        self.assertNotIn('scan_ready',[event[0] for event in list(events.queue)])

    def test_auto_save_does_not_archive_reviews_unassigned_or_first_page_errors(self):
        job_id=self.enqueue()
        self.settings.auto_save_scans=True
        worker=ScanWorker(self.store,queue.Queue(),self.settings)
        for state,first_error in (('review',False),('attachment',False),('review',True)):
            with self.subTest(state=state,first_error=first_error):
                self.store.update(job_id,status='queued')
                def analyze(page,*args,**kwargs):
                    page.state=state
                    page.first_page_error=first_error and page.index==0
                    return page
                with patch('arar.scanning.analyze_page',side_effect=analyze):
                    worker.analyze(self.store.get(job_id),self.settings)
                self.assertEqual(self.store.get(job_id)['status'],'review')
                self.assertFalse(Path(self.settings.archive_dir).exists())

    def test_auto_save_failure_keeps_review_and_working_copy(self):
        job_id=self.enqueue()
        self.settings.auto_save_scans=True
        worker=ScanWorker(self.store,queue.Queue(),self.settings)
        with patch('arar.scanning.analyze_page',side_effect=self.analyze_clean), \
                patch('arar.scanning.write_archive',side_effect=OSError('Disk full')):
            worker.analyze(self.store.get(job_id),self.settings)
        job=self.store.get(job_id)
        self.assertEqual(job['status'],'review')
        self.assertIn('Disk full',job['error'])
        self.assertTrue(Path(job['snapshot']).exists())

    def test_dismissed_jobs_stay_removed_after_restart_without_deleting_original(self):
        job_id=self.enqueue()
        job=self.store.get(job_id)
        self.store.update(job_id,status='review')
        self.assertEqual(self.store.dismiss([job_id]),[job_id])
        self.assertEqual(self.store.jobs(pending_only=True),[])
        self.assertTrue(self.source.exists())
        self.assertFalse(Path(job['snapshot']).exists())
        self.store.recover()
        self.assertEqual(self.store.get(job_id)['status'],'dismissed')
        restarted=FolderWatcher(ScanStore(self.root/'queue'))
        restarted.poll(self.settings,now=0)
        self.assertEqual(restarted.poll(self.settings,now=10)[0],[])

    def test_dismissing_running_analysis_prevents_result_resurrection_or_auto_save(self):
        job_id=self.enqueue()
        self.settings.auto_save_scans=True
        events=queue.Queue()
        worker=ScanWorker(self.store,events,self.settings)
        def analyze(page,*args,**kwargs):
            self.analyze_clean(page)
            self.assertEqual(self.store.dismiss([job_id]),[job_id])
            return page
        with patch('arar.scanning.analyze_page',side_effect=analyze) as analyzed:
            worker.analyze(self.store.get(job_id),self.settings)
        self.assertEqual(analyzed.call_count,1)
        self.assertEqual(self.store.get(job_id)['status'],'dismissed')
        self.assertNotIn('scan_ready',[event[0] for event in list(events.queue)])
        self.assertFalse(Path(self.settings.archive_dir).exists())

    def test_exporting_job_cannot_be_dismissed_or_started_by_another_worker(self):
        job_id=self.enqueue()
        job=self.store.get(job_id)
        self.store.update(job_id,status='exporting')
        self.assertEqual(self.store.dismiss([job_id]),[])
        self.assertEqual(self.store.get(job_id)['status'],'exporting')
        worker=ScanWorker(self.store,queue.Queue(),self.settings)
        with patch('arar.scanning.analyze_page') as analyze:
            worker.analyze(job,self.settings)
        analyze.assert_not_called()

    def test_date_archive_is_collision_safe_and_export_commit_recovers_after_restart(self):
        job_id=self.enqueue()
        job=self.store.jobs()[0]
        pages=decode_pages(job['pages'])
        pages[0].state='cover'
        pages[0].barcode='REPORT'
        pages[1].state='attachment'
        groups,_=build_groups(pages)
        now=datetime(2026,10,21,14,32,8)
        first=reserve_archive(self.settings.archive_dir,'Tarama_1',now)
        second=reserve_archive(self.settings.archive_dir,'Tarama_1',now)
        self.assertEqual(first.parent.name,'2026-10-21')
        self.assertEqual(first.name,'14-32-08_Tarama_1_001')
        self.assertEqual(second.name,'14-32-08_Tarama_1_002')
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
        folder=reserve_archive(self.settings.archive_dir,'Tarama_1')
        with self.assertRaises(IndexError):
            write_archive(groups,folder,job_id)
        self.assertEqual(list(folder.iterdir()),[])
        self.assertFalse(archive_committed(folder,job_id))

    def test_configuration_rejects_network_overlapping_and_missing_inputs(self):
        for fields in ({'input_dirs':[r'\\server\share']},
                       {'archive_dir':str(self.incoming/'archive')},
                       {'input_dirs':[str(self.incoming),str(self.incoming)]},
                       {'input_dirs':[]}, {'input_dirs':'not a list'}, {'input_dirs':['']}):
            with self.subTest(fields=fields):
                from dataclasses import replace
                with self.assertRaises(ValueError):
                    replace(self.settings,**fields).validate_scan_paths()

    def test_multiple_input_folders_are_numbered_and_all_are_watched(self):
        folders=[self.incoming]
        for index in range(2,5):
            folder=self.root/f'incoming{index}'
            folder.mkdir()
            (folder/'scan.pdf').write_bytes(self.source.read_bytes())
            folders.append(folder)
        self.settings.input_dirs=[str(folder) for folder in folders]
        self.watcher.poll(self.settings,now=0)
        added,errors=self.watcher.poll(self.settings,now=4)
        self.assertEqual(len(added),4)
        self.assertFalse(errors)
        self.assertEqual([job['label'] for job in self.store.jobs()],['Tarama_1','Tarama_2','Tarama_3','Tarama_4'])

    def test_old_settings_and_pending_jobs_migrate_without_losing_folders(self):
        import json
        folder=self.root/'legacy'
        directory=folder/'.arar'
        directory.mkdir(parents=True)
        other=self.root/'second'
        other.mkdir()
        old={'canon_input_dir':str(self.incoming),'kodak_input_dir':str(other),
             'auto_watch':True,'archive_dir':self.settings.archive_dir,'auto_save_scans':True}
        (directory/'settings.json').write_text(json.dumps(old),encoding='utf-8')
        with patch('arar.models.ROOT',folder):
            settings=Settings.load()
            self.assertEqual(settings.input_dirs,[str(self.incoming),str(other)])
            self.assertTrue(settings.auto_save_scans)
            settings.save()
            saved=json.loads((directory/'settings.json').read_text(encoding='utf-8'))
            self.assertNotIn('canon_input_dir',saved)
            self.assertEqual(Settings.load().input_dirs,settings.input_dirs)
        stat=self.source.stat()
        job_id=self.store.enqueue(self.source,'Canon',(stat.st_size,stat.st_mtime_ns))
        self.store.migrate_input_labels(settings)
        self.assertEqual(self.store.get(job_id)['label'],'Tarama_1')

    def test_new_empty_list_does_not_restore_old_legacy_folders(self):
        import json
        directory=self.root/'.arar'
        directory.mkdir()
        (directory/'settings.json').write_text(json.dumps({'input_dirs':[],
            'canon_input_dir':str(self.incoming),'archive_dir':self.settings.archive_dir}),encoding='utf-8')
        with patch('arar.models.ROOT',self.root):
            self.assertEqual(Settings.load().input_dirs,[])


class ApprovalProblemTests(unittest.TestCase):
    def pages(self,*states):
        return [PageResult('scan.pdf',index,barcode='REPORT' if state=='cover' else '',state=state)
                for index,state in enumerate(states)]

    def test_ready_scan_has_no_problem(self):
        self.assertEqual(approval_problem('review',self.pages('cover','attachment'),'shared'),'')

    def test_unfinished_statuses_explain_themselves(self):
        for status in ('queued','analyzing','exporting'):
            with self.subTest(status=status):
                self.assertTrue(approval_problem(status,[],'shared'))
        self.assertIn('Boom',approval_problem('error',[],'shared','Boom'))
        self.assertNotIn('..',approval_problem('error',[],'shared','Boom.'))

    def test_pages_waiting_for_a_decision_are_named(self):
        text=approval_problem('review',self.pages('cover','review','attachment','review'),'shared')
        self.assertIn('2 sayfa',text)
        self.assertIn('2, 4',text)

    def test_unanalyzed_and_numberless_cover_pages_have_their_own_messages(self):
        self.assertIn('henüz analiz edilmedi',approval_problem('review',self.pages('pending','pending'),'shared'))
        pages=self.pages('cover','attachment')
        pages[0].barcode=''
        self.assertIn('numarası yok',approval_problem('review',pages,'shared'))
        pages[0].manual_barcode='MANUAL'
        self.assertEqual(approval_problem('review',pages,'shared'),'')

    def test_advice_points_at_the_panel_when_pages_are_already_open(self):
        pages=self.pages('cover','review')
        self.assertIn('Taramayı inceleyip',approval_problem('review',pages,'shared'))
        text=approval_problem('review',pages,'shared',reviewing=True)
        self.assertIn('sağdaki panelden',text)
        self.assertNotIn('Taramayı',text)

    def test_decided_first_page_error_no_longer_blocks(self):
        pages=self.pages('review','attachment')
        pages[0].first_page_error=True
        self.assertIn('İlk sayfada',approval_problem('review',pages,'shared'))
        pages[0].decision='cover'
        pages[0].manual_barcode='MANUAL'
        self.assertEqual(approval_problem('review',pages,'shared'),'')

    def test_first_page_error_and_missing_cover_are_reported(self):
        pages=self.pages('attachment','attachment')
        self.assertIn('kapağa bağlanamadı',approval_problem('review',pages,'shared'))
        self.assertIn('kapak sayfasını belirleyin',approval_problem('review',pages,'shared'))
        self.assertIn('Kapak sayfası bulunamadı',approval_problem('review',[],'shared'))
        pages[0].first_page_error=True
        self.assertIn('İlk sayfada',approval_problem('review',pages,'shared'))


if __name__=='__main__':
    unittest.main()
