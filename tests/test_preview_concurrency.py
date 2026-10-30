"""A slow OCR/stamp stage must not block another PDF preview."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from local_dependencies import activate_local_dependencies
activate_local_dependencies()
from pypdf import PdfWriter
from arar.detection import analyze_page,list_pages,render_page,_load_analysis_page


class PreviewConcurrencyTests(unittest.TestCase):
    def test_preview_finishes_while_ocr_or_stamp_analysis_is_waiting(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'page.pdf'
            writer=PdfWriter()
            writer.add_blank_page(width=100,height=150)
            with source.open('wb') as handle:
                writer.write(handle)
            for stage in ('ocr','stamps'):
                with self.subTest(stage=stage):
                    entered=threading.Event()
                    release=threading.Event()
                    def gate():
                        entered.set()
                        if not release.wait(10):
                            raise TimeoutError('Analysis was not released')
                    def ocr(*args):
                        if stage=='ocr': gate()
                        return 0,[]
                    def stamps(*args,**kwargs):
                        if stage=='stamps': gate()
                        return []
                    with patch('arar.detection.find_report_headings',side_effect=ocr), \
                            patch('arar.detection._scan_stamps',side_effect=stamps), \
                            ThreadPoolExecutor(max_workers=2) as pool:
                        analysis=pool.submit(analyze_page,list_pages(source)[0])
                        try:
                            self.assertTrue(entered.wait(5))
                            preview=pool.submit(render_page,source,0,(200,300))
                            image,size=preview.result(timeout=3)
                            self.assertEqual(image.size,(200,300))
                            self.assertFalse(analysis.done())
                        finally:
                            release.set()
                        analysis.result(timeout=5)

    def test_cancelled_load_does_not_open_pdf(self):
        cancel=threading.Event()
        cancel.set()
        with patch('arar.detection.pdfium.PdfDocument') as open_pdf:
            self.assertIsNone(_load_analysis_page('unused.pdf',0,cancel))
            open_pdf.assert_not_called()
