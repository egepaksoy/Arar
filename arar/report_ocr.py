"""Offline text location for Receiving Report headings (no barcode OCR)."""
from dataclasses import dataclass
import os
import re

from PIL import Image, ImageOps
from tesserocr import OEM, PSM, RIL, PyTessBaseAPI, iterate_level

from .models import ROOT

TESSDATA = ROOT / 'assets' / 'tessdata'


@dataclass(frozen=True)
class Word:
    text: str
    box: tuple[float, float, float, float]
    confidence: float


@dataclass(frozen=True)
class ReportHeading:
    box: tuple[float, float, float, float]
    confidence: float


def tessdata_path():
    """Tesseract's Windows file API needs an ASCII path, even for Turkish users."""
    path = TESSDATA.resolve()
    if not (path / 'eng.traineddata').is_file():
        raise RuntimeError('OCR dil dosyası eksik: assets/tessdata/eng.traineddata. Arar kurulumunu yenileyin.')
    if os.name == 'nt':
        try:
            relative = os.path.relpath(path)
            if relative.isascii():
                return relative
        except ValueError:  # Different Windows drives.
            pass
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer)):
            return buffer.value
    return str(path)


def _normalized(text):
    return re.sub('[^A-Z0-9]', '', text.upper())


def _one_typo(text, expected):
    """Allow at most one substitution/insertion/deletion in a long word."""
    if text == expected:
        return True
    if abs(len(text)-len(expected)) > 1:
        return False
    if len(text) == len(expected):
        return sum(a != b for a, b in zip(text, expected)) <= 1
    short, long = sorted((text, expected), key=len)
    return any(long[:i]+long[i+1:] == short for i in range(len(long)))


def headings_from_words(words):
    """Match words and spatial adjacency, independently of font and ink color."""
    headings = []
    for first in words:
        if first.confidence < 40 or not _one_typo(_normalized(first.text), 'RECEIVING'):
            continue
        height = first.box[3]-first.box[1]
        if height <= 0:
            continue
        following = sorted((w for w in words if w.box[0] >= first.box[2]-height*.2
                            and abs((w.box[1]+w.box[3]-first.box[1]-first.box[3])/2) < height*.65),
                           key=lambda w: w.box[0])
        if len(following) < 2:
            continue
        report, number = following[:2]
        if (report.confidence < 40 or number.confidence < 30
                or not _one_typo(_normalized(report.text), 'REPORT')
                or _normalized(number.text).replace('0', 'O') != 'NO'
                or report.box[0]-first.box[2] > height*2.5
                or number.box[0]-report.box[2] > height*2.5):
            continue
        box = (first.box[0], min(first.box[1], report.box[1], number.box[1]),
               number.box[2], max(first.box[3], report.box[3], number.box[3]))
        headings.append(ReportHeading(box, min(first.confidence, report.confidence, number.confidence)/100))
    return headings


def find_report_headings(image, cancel=None):
    """Return rotation and heading boxes in the oriented ORIGINAL image's pixels."""
    if cancel is not None and cancel.is_set():
        return 0, []
    gray = image.convert('L')
    if gray.getextrema()[0] >= 245:  # Blank pages need no OCR.
        return 0, []
    factor = min(1., 2400/max(image.size))
    size = (max(1, round(image.width*factor)), max(1, round(image.height*factor)))
    small = ImageOps.autocontrast(gray.resize(size, Image.Resampling.LANCZOS))
    with PyTessBaseAPI(path=tessdata_path(), lang='eng', oem=OEM.LSTM_ONLY,
                       psm=PSM.SPARSE_TEXT) as api:
        api.SetVariable('debug_file', os.devnull)
        for rotation in (0, 90, 180, 270):
            if cancel is not None and cancel.is_set():
                return 0, []
            oriented = small.rotate(rotation, expand=True)
            api.SetImage(oriented)
            api.SetSourceResolution(200)
            if not api.Recognize(timeout=5000):
                raise RuntimeError('Yazı tanıma zamanında tamamlanamadı. Sayfa yeniden incelenmeli.')
            iterator = api.GetIterator()
            words = []
            if iterator is not None:
                for item in iterate_level(iterator, RIL.WORD):
                    if item.Empty(RIL.WORD):
                        continue
                    text, box = item.GetUTF8Text(RIL.WORD), item.BoundingBox(RIL.WORD)
                    if text and box:
                        words.append(Word(text, box, item.Confidence(RIL.WORD)))
            headings = headings_from_words(words)
            if headings:
                width, height = image.size if rotation in (0, 180) else image.size[::-1]
                sx, sy = width/oriented.width, height/oriented.height
                return rotation, [ReportHeading((h.box[0]*sx, h.box[1]*sy,
                                                  h.box[2]*sx, h.box[3]*sy), h.confidence)
                                  for h in headings]
    return 0, []
