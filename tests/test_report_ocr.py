from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from local_dependencies import activate_local_dependencies
activate_local_dependencies()
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from arar.barcodes import WIDTHS, barcode_regions
from arar.detection import analyze_page, list_pages
from arar.models import ROOT
from arar.report_ocr import heading_distance, strip_heading
from arar.stamps import Stamp


def barcode_image(value, checksum_error=0):
    symbols=[104]+[ord(c)-32 for c in value]
    symbols += [((symbols[0]+sum(i*v for i,v in enumerate(symbols[1:],1)))+checksum_error)%103,106]
    row=[False]*30
    black=True
    for width in [int(c) for symbol in symbols for c in WIDTHS[symbol]]:
        row.extend([black]*width*3)
        black=not black
    row.extend([False]*30)
    return Image.fromarray(np.where(np.tile(row,(70,1)),0,255).astype('uint8'))


def report_image(value='NEW1234567', with_barcode=True, checksum_error=0):
    image=Image.new('RGB',(1500,1050),(236,239,242))
    draw=ImageDraw.Draw(image)
    font=ImageFont.load_default(size=32)
    text='Receiving Report No.'
    draw.text((90,160),text,font=font,fill=(40,45,80))
    box=draw.textbbox((90,160),text,font=font)
    if with_barcode:
        image.paste(barcode_image(value,checksum_error),(60,box[3]+8))
    draw.text((870,160),'PART NO',font=font,fill='black')
    image.paste(barcode_image('PRODUCT123'),(840,box[3]+8))
    return image,box


BLUE=[Stamp('blue',(1,1,20,20),.95)]


class HeadingTests(unittest.TestCase):
    def test_heading_text_tolerates_ocr_slips_but_not_other_labels(self):
        for text in ('RECEIVING REPORT NO','Receiving Report No.','RECEIVlNG REP0RT N0','RECEIVING REPORTNO'):
            with self.subTest(text=text):
                self.assertLessEqual(heading_distance(text),3)
        for text in ('PART NO UM113T143500100F','LAST LOGISTIC LOCATION','RECEIVING REPORT','SUPPLIER PART NO'):
            with self.subTest(text=text):
                self.assertGreater(heading_distance(text),3)

    def test_heading_strip_is_read_with_real_ocr(self):
        label=np.asarray(Image.open(ROOT/'assets/receiving_report.png').convert('L'))
        self.assertGreater(strip_heading(label[:50]),.8)
        self.assertEqual(strip_heading(label[55:]),0.)          # the bars alone
        self.assertEqual(strip_heading(np.full((40,300),230,np.uint8)),0.)

    def test_bars_are_found_but_text_lines_are_not(self):
        image,_=report_image()
        draw=ImageDraw.Draw(image)
        font=ImageFont.load_default(size=28)
        for y in range(600,1000,40):
            draw.text((60,y),'Lorem ipsum dolor sit amet consectetur 1234567890',font=font,fill='black')
        regions=barcode_regions(np.asarray(image.convert('L')),288)
        self.assertEqual(len(regions),2)
        self.assertTrue(all(r.box[1]>150 and r.box[3]<320 for r in regions))


class ReportFlowTests(unittest.TestCase):
    def analyze(self,image,stamps=(),**kwargs):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'scan.pdf'
            image.save(source,'PDF',resolution=288,quality=100)
            with patch('arar.detection.find_stamps',return_value=list(stamps)):
                return analyze_page(list_pages(source)[0],**kwargs)

    def test_report_barcode_is_told_apart_by_its_heading(self):
        result=self.analyze(report_image()[0],BLUE)
        self.assertEqual(result.barcode,'NEW1234567')
        self.assertTrue(result.target_found)
        self.assertIn('PRODUCT123',result.other_barcodes)
        self.assertTrue(any(e.kind=='heading' for e in result.evidence))
        self.assertEqual(result.state,'cover')

    def test_rotated_and_upside_down_pages_are_read(self):
        image,_=report_image()
        for rotation in (90,180,270):
            with self.subTest(rotation=rotation):
                result=self.analyze(image.rotate(rotation,expand=True,fillcolor=(236,239,242)))
                self.assertEqual(result.barcode,'NEW1234567')
                self.assertIn('PRODUCT123',result.other_barcodes)

    def test_supplied_label_image_alone(self):
        result=self.analyze(Image.open(ROOT/'assets/receiving_report.png').convert('RGB'))
        self.assertEqual(result.barcode,'THAEK12026124')

    def test_unreadable_report_requires_review_even_with_blue_stamp(self):
        image,_=report_image(checksum_error=1)
        result=self.analyze(image,BLUE,review_missing_stamp=False)
        self.assertTrue(result.target_found)
        self.assertFalse(result.barcode)
        self.assertFalse(result.first_page_error)
        self.assertEqual(result.state,'review')
        self.assertIn('yazısı bulundu',result.reason)

    def test_missing_report_barcode_does_not_adopt_adjacent_product(self):
        result=self.analyze(report_image(with_barcode=False)[0],BLUE)
        self.assertFalse(result.target_found)
        self.assertFalse(result.barcode)
        self.assertEqual(result.other_barcodes,['PRODUCT123'])
        self.assertEqual(result.state,'attachment')

    def test_conflicting_codes_under_header_require_review(self):
        image,box=report_image()
        image.paste(barcode_image('SECOND1234'),(60,box[3]+90))
        result=self.analyze(image,BLUE)
        self.assertEqual(result.state,'review')
        self.assertFalse(result.barcode)
        self.assertIn('Birden fazla',result.reason)


if __name__=='__main__':
    unittest.main()
