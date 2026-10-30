from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from local_dependencies import activate_local_dependencies
activate_local_dependencies()
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from arar.barcodes import WIDTHS, read_barcodes
from arar.detection import analyze_page, list_pages, _barcodes_below_heading, heading_score
from arar.models import ROOT, Evidence
from arar.report_ocr import Word, ReportHeading, headings_from_words, find_report_headings


def barcode_image(value):
    symbols=[104]+[ord(c)-32 for c in value]
    symbols += [(symbols[0]+sum(i*v for i,v in enumerate(symbols[1:],1)))%103,106]
    row=[False]*30
    black=True
    for width in [int(c) for symbol in symbols for c in WIDTHS[symbol]]:
        row.extend([black]*width*3)
        black=not black
    row.extend([False]*30)
    return Image.fromarray(np.where(np.tile(row,(70,1)),0,255).astype('uint8'))


def report_image(gap=8, value='NEW1234567', with_barcode=True):
    image=Image.new('RGB',(1500,1050),(236,239,242))
    draw=ImageDraw.Draw(image)
    font=ImageFont.load_default(size=32)
    text='Receiving Report No.'
    draw.text((90,160),text,font=font,fill=(40,45,80))
    box=draw.textbbox((90,160),text,font=font)
    if with_barcode:
        image.paste(barcode_image(value),(60,box[3]+gap))
    draw.text((870,160),'PART NO',font=font,fill='black')
    image.paste(barcode_image('PRODUCT123'),(840,box[3]+8))
    return image,ReportHeading(box,.95)


class HeadingTests(unittest.TestCase):
    def test_words_allow_case_punctuation_and_one_typo_but_require_adjacency(self):
        words=[Word('receivlng',(10,20,100,40),95),Word('Report',(110,20,170,40),95),
               Word('N0.',(180,20,210,40),90)]
        self.assertEqual(len(headings_from_words(words)),1)
        self.assertFalse(headings_from_words(words[:2]))
        self.assertFalse(headings_from_words([words[0],Word('Report',(110,120,170,140),95),words[2]]))
        self.assertFalse(headings_from_words([Word('Shipping',words[0].box,95),*words[1:]]))

    def test_real_ocr_handles_a_different_font_tinted_paper_and_rotation(self):
        image,_=report_image()
        for rotation in (0,90,180,270):
            with self.subTest(rotation=rotation):
                found_rotation,headings=find_report_headings(image.rotate(rotation,expand=True))
                self.assertEqual((rotation+found_rotation)%360,0)
                self.assertEqual(len(headings),1)
                bars=_barcodes_below_heading(image,headings[0])
                self.assertEqual({b.value for b in bars},{'NEW1234567'})

    def test_cancelled_ocr_does_not_start_engine(self):
        stop=threading.Event()
        stop.set()
        with patch('arar.report_ocr.PyTessBaseAPI') as engine:
            self.assertEqual(find_report_headings(Image.new('RGB',(50,50),'black'),stop),(0,[]))
            engine.assert_not_called()

    def test_expanded_search_finds_lower_barcode_and_excludes_neighbor(self):
        image,heading=report_image(gap=180)
        with patch('arar.detection.read_barcodes',wraps=read_barcodes) as read:
            bars=_barcodes_below_heading(image,heading)
        self.assertGreaterEqual(read.call_count,3)  # narrow + contrast + wider
        self.assertEqual({b.value for b in bars},{'NEW1234567'})
        self.assertGreater(min(b.box[1] for b in bars),heading.box[3]+150)

    def test_missing_report_barcode_does_not_adopt_adjacent_product(self):
        image,heading=report_image(with_barcode=False)
        self.assertFalse(_barcodes_below_heading(image,heading))

    def test_expanded_search_recovers_barcode_cut_by_narrow_right_edge(self):
        image,heading=report_image(with_barcode=False)
        image.paste((236,239,242),(800,0,1500,1050))
        value='LONG12345678901234567'
        image.paste(barcode_image(value),(60,heading.box[3]+8))
        with patch('arar.detection.read_barcodes',wraps=read_barcodes) as read:
            bars=_barcodes_below_heading(image,heading)
        self.assertGreaterEqual(read.call_count,3)
        self.assertEqual({b.value for b in bars},{value})


class ReportFlowTests(unittest.TestCase):
    def analyze(self,image,**kwargs):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'scan.pdf'
            image.save(source,'PDF',resolution=288,quality=100)
            return analyze_page(list_pages(source)[0],**kwargs)

    def test_ocr_precedes_and_bypasses_asset_match(self):
        image,_=report_image()
        with patch('arar.detection.heading_score',side_effect=AssertionError('Asset fallback used despite OCR')), \
                patch('arar.detection._scan_stamps',return_value=[]):
            result=self.analyze(image)
        self.assertEqual(result.barcode,'NEW1234567')
        self.assertTrue(result.target_found)
        self.assertIn('PRODUCT123',result.other_barcodes)
        self.assertTrue(any(e.kind=='heading' for e in result.evidence))

    def test_asset_fallback_only_when_ocr_has_no_heading(self):
        image=Image.open(ROOT/'assets/receiving_report.png').convert('RGB')
        with patch('arar.detection.find_report_headings',return_value=(0,[])), \
                patch('arar.detection.heading_score',wraps=heading_score) as match, \
                patch('arar.detection._scan_stamps',return_value=[]):
            result=self.analyze(image)
        self.assertTrue(match.called)
        self.assertEqual(result.barcode,'THAEK12026124')

    def test_unreadable_report_requires_review_even_with_blue_stamp(self):
        image,_=report_image(with_barcode=False)
        with patch('arar.detection.heading_score',side_effect=AssertionError('Must not fall back')), \
                patch('arar.detection._scan_stamps',return_value=[Evidence('blue',(1,1,20,20),.95)]):
            result=self.analyze(image,review_other_barcodes=False,review_missing_stamp=False)
        self.assertTrue(result.target_found)
        self.assertFalse(result.barcode)
        self.assertFalse(result.first_page_error)
        self.assertEqual(result.state,'review')
        self.assertIn('yazısı bulundu',result.reason)

    def test_conflicting_codes_under_header_require_review(self):
        image,heading=report_image()
        image.paste(barcode_image('SECOND1234'),(60,heading.box[3]+90))
        with patch('arar.detection._scan_stamps',return_value=[Evidence('blue',(1,1,20,20),.95)]):
            result=self.analyze(image)
        self.assertEqual(result.state,'review')
        self.assertFalse(result.barcode)
        self.assertIn('Birden fazla',result.reason)


if __name__=='__main__':
    unittest.main()
