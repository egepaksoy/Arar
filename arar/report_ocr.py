"""Offline reading of the RECEIVING REPORT NO heading next to a barcode (no barcode OCR)."""
import os
import re
import threading

import numpy as np
from PIL import Image
from tesserocr import OEM, PSM, PyTessBaseAPI

from .models import ROOT

TESSDATA = ROOT / 'assets' / 'tessdata'


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


HEADING = 'RECEIVINGREPORTNO'
_LOOKALIKE = str.maketrans({'0': 'O', '1': 'I', 'L': 'I', '|': 'I', '!': 'I', '5': 'S', '8': 'B'})
_local = threading.local()


def _strip_api():
    """One Tesseract engine per thread; loading the model costs more than a strip."""
    api = getattr(_local, 'api', None)
    if api is None:
        api = PyTessBaseAPI(path=tessdata_path(), lang='eng', oem=OEM.LSTM_ONLY, psm=PSM.AUTO)
        api.SetVariable('debug_file', os.devnull)
        _local.api = api
    return api


def _infix_distance(text, pattern):
    """Fewest edits that turn some part of ``text`` into ``pattern``."""
    previous = [0]*(len(text)+1)   # the pattern may start anywhere in the text
    for i, letter in enumerate(pattern, 1):
        current = [i]+[0]*len(text)
        for j, char in enumerate(text, 1):
            current[j] = min(previous[j]+1, current[j-1]+1, previous[j-1]+(letter != char))
        previous = current
    return min(previous)


def heading_distance(text):
    """OCR edits between ``text`` and RECEIVING REPORT NO.

    The 'REPORT NO' part may differ by one edit at most, so a page title
    reading RECEIVING REPORT alone is never taken for the barcode heading.
    """
    text = re.sub('[^A-Z0-9|!]', '', text.upper()).translate(_LOOKALIKE)
    pattern = HEADING.translate(_LOOKALIKE)
    if _infix_distance(text, pattern[-8:]) > 1:
        return len(pattern)
    return _infix_distance(text, pattern)


def strip_heading(gray):
    """Confidence (0-1) that an upright text strip reads RECEIVING REPORT NO.

    The strip is the narrow band next to a barcode, so a few OCR errors are
    tolerated: unrelated headings such as PART NO are far more than three
    edits away.
    """
    if gray.size == 0 or int(gray.max())-int(gray.min()) < 40:
        return 0.
    # Tesseract needs a margin; strips are cut right at the text.
    margin = max(8, gray.shape[0]//4)
    paper = int(np.percentile(gray, 90))
    gray = np.pad(gray, margin, constant_values=paper)
    api = _strip_api()
    api.SetImage(Image.fromarray(gray))
    api.SetSourceResolution(300)
    if not api.Recognize(timeout=3000):
        return 0.
    distance = heading_distance(api.GetUTF8Text() or '')
    return max(0., 1-distance/len(HEADING)) if distance <= 3 else 0.
