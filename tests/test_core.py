from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from local_dependencies import activate_local_dependencies
activate_local_dependencies()
import numpy as np
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
from arar.barcodes import WIDTHS, read_barcodes
from arar.detection import analyze_page, list_pages, render_page
from arar.exporter import export_groups, safe_filename
from arar.models import PageResult, DocumentGroup, Settings, build_groups, ROOT
from arar.offline import local_path

EXAMPLES_AVAILABLE=all((ROOT/'Örnek/Kolay'/f'Örnek-{i}.pdf').is_file() for i in (1,3,4,6,9))
requires_examples=unittest.skipUnless(EXAMPLES_AVAILABLE,'Yerel örnek PDF’ler depoya dahil değildir.')


def page(i,state='attachment',source='a.pdf',number=''):
    return PageResult(source,i,barcode=number,state=state)


class SettingsTests(unittest.TestCase):
    def test_older_settings_keep_cover_confirmation_enabled(self):
        with tempfile.TemporaryDirectory() as folder,patch('arar.models.ROOT',Path(folder)):
            settings_dir=Path(folder)/'.arar'
            settings_dir.mkdir()
            (settings_dir/'settings.json').write_text('{"grouping":"shared"}',encoding='utf-8')
            settings=Settings.load()
            self.assertEqual(settings.grouping,'shared')
            self.assertTrue(settings.confirm_cover)
            self.assertTrue(settings.notify_analysis_done)

    def test_cover_confirmation_choice_survives_reload(self):
        with tempfile.TemporaryDirectory() as folder,patch('arar.models.ROOT',Path(folder)):
            settings=Settings()
            for enabled in (False,True):
                with self.subTest(enabled=enabled):
                    settings.confirm_cover=enabled
                    settings.notify_analysis_done=enabled
                    settings.save()
                    self.assertEqual(Settings.load().confirm_cover,enabled)
                    self.assertEqual(Settings.load().notify_analysis_done,enabled)


class GroupingTests(unittest.TestCase):
    def test_worker_result_retains_manual_decision_and_number(self):
        current=page(0,'review',number='AUTO')
        current.decision='cover'
        current.manual_barcode='MANUAL'
        result=page(0,'review',number='NEW-AUTO')
        result.stamp='black'
        current.apply_analysis(result)
        self.assertEqual((current.effective_state,current.number),('cover','MANUAL'))
        self.assertEqual((current.state,current.barcode,current.stamp),('review','NEW-AUTO','black'))

    def test_worker_result_cannot_apply_to_different_page(self):
        with self.assertRaises(ValueError):
            page(0).apply_analysis(page(1))

    def test_sequential_boundaries_and_preserved_order(self):
        pages=[page(0,'cover',number='A'),page(1),page(2,'cover',number='B'),page(3)]
        groups,left=build_groups(pages,'sequential')
        self.assertFalse(left)
        self.assertEqual([[p.index for p in g.pages] for g in groups],[[0,1],[2,3]])

    def test_shared_adjacent_covers_and_next_batch(self):
        pages=[page(0,'cover',number='A'),page(1,'cover',number='B'),page(2),page(3),
               page(4,'cover',number='C'),page(5)]
        groups,left=build_groups(pages,'shared')
        self.assertFalse(left)
        self.assertEqual([[p.index for p in g.pages] for g in groups],[[0,2,3],[1,2,3],[4,5]])

    def test_review_blocks_following_assignment_until_decision(self):
        pages=[page(0,'cover',number='A'),page(1,'review'),page(2)]
        groups,left=build_groups(pages)
        self.assertEqual([p.index for p in left],[1,2])
        self.assertEqual([p.index for p in groups[0].pages],[0])
        pages[1].decision='attachment'
        groups,left=build_groups(pages)
        self.assertFalse(left)
        self.assertEqual([p.index for p in groups[0].pages],[0,1,2])

    def test_sources_never_join_and_prefix_never_dropped(self):
        pages=[page(0),page(1,'cover',number='A'),page(0,source='b.pdf')]
        groups,left=build_groups(pages)
        self.assertEqual(len(left),2)
        self.assertEqual(len(groups[0].pages),1)

    def test_cover_without_number_is_unassigned(self):
        groups,left=build_groups([page(0,'cover'),page(1)])
        self.assertFalse(groups)
        self.assertEqual(len(left),2)


class DetectionTests(unittest.TestCase):
    @requires_examples
    def test_raster_scan_requires_manual_stamp_confirmation(self):
        image,_=render_page(ROOT/'Örnek/Kolay/Örnek-3.pdf',0,(2600,3600))
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'scan.pdf'
            image.save(source,'PDF',resolution=288)
            result=analyze_page(list_pages(source)[0])
            self.assertEqual(result.barcode,'THAEK12026124')
            self.assertEqual(result.state,'review')
            self.assertEqual(result.stamp,'blue')

    @requires_examples
    def test_receiving_barcode_and_product_barcode_are_distinct(self):
        result=analyze_page(list_pages(ROOT/'Örnek/Kolay/Örnek-1.pdf')[0])
        self.assertEqual(result.barcode,'THAEK12026124')
        self.assertIn('UM113T142500000F',result.other_barcodes)
        self.assertEqual(result.state,'cover')

    @requires_examples
    def test_stamp_rules_from_supplied_examples(self):
        for name,stamp,state in [('Örnek-3','blue','cover'),('Örnek-4','faint','review'),
                                 ('Örnek-6','black','review'),('Örnek-9','mixed','review')]:
            with self.subTest(name=name):
                result=analyze_page(list_pages(ROOT/'Örnek/Kolay'/f'{name}.pdf')[0])
                self.assertEqual((result.stamp,result.state),(stamp,state))
                self.assertTrue(result.target_found)

    @requires_examples
    def test_attachment_has_no_target(self):
        result=analyze_page(list_pages(ROOT/'Örnek/Kolay/Örnek-3.pdf')[1])
        self.assertEqual(result.state,'attachment')
        self.assertFalse(result.target_found)

    def test_code39_reference_requires_consistent_scan_lines(self):
        image=Image.open(ROOT/'assets/receiving_report.png')
        values=read_barcodes(image,2)
        self.assertEqual([v.value for v in values],['THAEK12026124'])

    def test_code128_checksum_accepts_valid_and_rejects_corrupt(self):
        def image(symbols):
            runs=[int(c) for v in symbols for c in WIDTHS[v]]
            row=[False]*30
            color=True
            for width in runs:
                row.extend([color]*width*3)
                color=not color
            row.extend([False]*30)
            gray=np.where(np.tile(row,(60,1)),0,255).astype('uint8')
            return Image.fromarray(gray)
        valid=[104,33,34,(104+33+2*34)%103,106]
        self.assertEqual([b.value for b in read_barcodes(image(valid),4)],['AB'])
        valid[-2]=(valid[-2]+1)%103
        self.assertEqual(read_barcodes(image(valid),4),[])


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.scratch=tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.source=Path(self.scratch.name)/'fixture.pdf'
        writer=PdfWriter()
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),
                               NameObject('/Subtype'):NameObject('/Type1'),
                               NameObject('/BaseFont'):NameObject('/Helvetica')})
        for i in range(2):
            fixture=writer.add_blank_page(width=595-i*100,height=842-i*100)
            fixture[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):
                DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
            stream=DecodedStreamObject()
            stream.set_data(f'BT /F1 18 Tf 30 100 Td (Fixture page {i+1}) Tj ET'.encode('ascii'))
            fixture[NameObject('/Contents')]=writer._add_object(stream)
        with self.source.open('wb') as handle:
            writer.write(handle)

    def test_changed_source_cannot_export_stale_analysis(self):
        import shutil
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.pdf'
            shutil.copyfile(self.source,source)
            pages=list_pages(source)
            group=DocumentGroup('A',pages)
            with source.open('ab') as stream:
                stream.write(b'\n% changed after import\n')
            with self.assertRaisesRegex(ValueError,'değişmiş'):
                export_groups([group],Path(folder)/'out')

    def test_copy_pages_collision_names_and_report(self):
        source=str(self.source)
        group=DocumentGroup('THAEK12026124',[page(0,'cover',source,'THAEK12026124'),page(1,source=source)])
        with tempfile.TemporaryDirectory() as folder:
            first=export_groups([group],folder)
            original_bytes=first[0].read_bytes()
            second=export_groups([group],folder)
            self.assertNotEqual(first[0],second[0])
            self.assertEqual(first[0].read_bytes(),original_bytes)
            self.assertEqual(len(PdfReader(second[0]).pages),2)
            source_reader=PdfReader(source)
            copied=PdfReader(second[0])
            self.assertEqual(copied.pages[0].extract_text(),'Fixture page 1')
            self.assertEqual(copied.pages[1].extract_text(),'Fixture page 2')
            self.assertEqual(copied.pages[1].extract_text(),source_reader.pages[1].extract_text())
            self.assertTrue(second[-1].name.endswith('.json'))

    def test_batch_failure_rolls_back_and_preserves_existing_files(self):
        source=str(self.source)
        groups=[DocumentGroup('A',[page(0,'cover',source,'A')]),
                DocumentGroup('B',[page(999,'cover',source,'B')])]
        with tempfile.TemporaryDirectory() as folder:
            keep=Path(folder)/'A.pdf'
            keep.write_bytes(b'existing')
            with self.assertRaises(IndexError):
                export_groups(groups,folder)
            self.assertEqual(list(Path(folder).iterdir()),[keep])
            self.assertEqual(keep.read_bytes(),b'existing')

    def test_windows_safe_names(self):
        self.assertEqual(safe_filename('CON'),'_CON')
        self.assertEqual(safe_filename('a/b:c'),'a_b_c')


class OfflineTests(unittest.TestCase):
    def test_rejects_unc_and_urls(self):
        for path in [r'\\server\share\file.pdf','//server/share','https://example.com']:
            with self.subTest(path=path),self.assertRaises(ValueError):
                local_path(path)

    def test_guard_blocks_connections_listeners_and_dns(self):
        import subprocess,sys
        code='''from arar.offline import install_network_guard
install_network_guard()
import socket
operations = [lambda: socket.socket(), lambda: socket.create_connection(('127.0.0.1',80)),
              lambda: socket.SocketType(),lambda: socket.create_server(('127.0.0.1',8000)),
              lambda: socket.getaddrinfo('example.com',443),lambda: socket.getnameinfo(('127.0.0.1',80),0)]
for operation in operations:
    try: operation()
    except PermissionError: pass
    else: raise AssertionError('Network operation was not blocked')
print('offline_ok')
'''
        result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('offline_ok',result.stdout)


if __name__=='__main__':
    unittest.main()
