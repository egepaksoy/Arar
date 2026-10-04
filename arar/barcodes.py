"""Offline Code 128 reader: run lengths, symbol fitting, mandatory checksum.

The table below is the standard Code 128 symbol width table. Unsupported or
damaged barcodes return no value, leaving the page for manual review.
"""
import numpy as np
from dataclasses import dataclass

WIDTHS = '''212222 222122 222221 121223 121322 131222 122213 122312 132212
221213 221312 231212 112232 122132 122231 113222 123122 123221 223211 221132
221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 212123
212321 232121 111323 131123 131321 112313 132113 132311 211313 231113 231311
112133 112331 132131 113123 113321 133121 313121 211331 231131 213113 213311
213131 311123 311321 331121 312113 312311 332111 314111 221411 431111 111224
111422 121124 121421 141122 141221 112214 112412 122114 122411 142112 142211
241211 221114 413111 241112 134111 111242 121142 121241 114212 124112 124211
411212 421112 421211 212141 214121 412121 111143 111341 131141 114113 114311
411113 411311 113141 114131 311141 411131 211412 211214 211232 2331112'''.split()
TABLE = np.array([[int(c) for c in word] for word in WIDTHS[:106]], dtype=float)
CODE39_RAW = {
    '0':'bsbSBsBsb','1':'BsbSbsbsB','2':'bsBSbsbsB','3':'BsBSbsbsb',
    '4':'bsbSBsbsB','5':'BsbSBsbsb','6':'bsBSBsbsb','7':'bsbSbsBsB',
    '8':'BsbSbsBsb','9':'bsBSbsBsb','A':'BsbsbSbsB','B':'bsBsbSbsB',
    'C':'BsBsbSbsb','D':'bsbsBSbsB','E':'BsbsBSbsb','F':'bsBsBSbsb',
    'G':'bsbsbSBsB','H':'BsbsbSBsb','I':'bsBsbSBsb','J':'bsbsBSBsb',
    'K':'BsbsbsbSB','L':'bsBsbsbSB','M':'BsBsbsbSb','N':'bsbsBsbSB',
    'O':'BsbsBsbSb','P':'bsBsBsbSb','Q':'bsbsbsBSB','R':'BsbsbsBSb',
    'S':'bsBsbsBSb','T':'bsbsBsBSb','U':'BSbsbsbsB','V':'bSBsbsbsB',
    'W':'BSBsbsbsb','X':'bSbsBsbsB','Y':'BSbsBsbsb','Z':'bSBsBsbsb',
    '-':'bSbsbsBsB','.':'BSbsbsBsb',' ':'bSBsbsBsb','*':'bSbsBsBsb',
    '$':'bSbSbSbsb','/':'bSbSbsbSb','+':'bSbsbSbSb','%':'bsbSbSbSb',
}
CODE39 = {tuple(c.isupper() for c in p): ch for ch,p in CODE39_RAW.items()}


@dataclass
class Barcode:
    value: str
    box: tuple[int, int, int, int]
    score: float
    kind: str = 'Code 128'


def read_code39_line(line,y):
    edges = np.flatnonzero(np.r_[True,line[1:] != line[:-1],True])
    runs = np.diff(edges)
    bits = line[edges[:-1]]
    result = []
    starts=np.flatnonzero(bits)
    starts=starts[starts+9<=len(runs)]
    if not len(starts):
        return result
    windows=np.lib.stride_tricks.sliding_window_view(runs,9)[starts].astype(float)
    sorted_widths=np.sort(windows,axis=1)
    small=sorted_widths[:,:6].mean(axis=1)
    large=sorted_widths[:,6:].mean(axis=1)
    pattern=windows>((small+large)/2)[:,None]
    star=np.array([c.isupper() for c in CODE39_RAW['*']])
    quiet=np.where(starts==0,True,runs[np.maximum(starts-1,0)]>=3*small)
    matches=np.all(pattern==star,axis=1)&(large/small>=1.45)&(large/small<=3.5)&quiet
    for start in starts[matches]:
        pos, letters, scores = start, [], []
        while pos+9 <= len(runs) and len(letters) < 100:
            widths = runs[pos:pos+9].astype(float)
            order = np.argsort(widths)
            narrow,wide = np.mean(widths[order[:6]]),np.mean(widths[order[6:]])
            if not 1.45 <= wide/narrow <= 3.5:
                break
            pattern = tuple(widths > (wide+narrow)/2)
            character = CODE39.get(pattern)
            error = np.max(np.abs(widths-np.where(pattern,wide,narrow)))/narrow
            if character is None or error > 0.65:
                break
            if not letters and character != '*':
                break
            scores.append(1-error/2)
            if letters and character == '*':
                if len(letters)>1 and (not start or runs[start-1] >= 3*narrow):
                    end = pos+9
                    if end == len(runs) or runs[end] >= 3*narrow:
                        result.append(Barcode(''.join(letters[1:]),
                            (int(edges[start]),y,int(edges[end]),y+1),min(scores),'Code 39'))
                break
            letters.append(character)
            if pos+9 >= len(runs) or runs[pos+9] > narrow*1.8:
                break
            pos += 10
    return result


def _symbol(runs, start=False):
    widths = np.asarray(runs, dtype=float)
    total = widths.sum()
    if total < 8:
        return None
    normalized = widths * 11 / total
    table = TABLE[103:106] if start else TABLE
    errors = np.mean((table - normalized)**2, axis=1)
    index = int(np.argmin(errors))
    if errors[index] > 0.22:
        return None
    return index + (103 if start else 0), float(errors[index])


def _decode_values(values):
    if len(values) < 3:
        return None
    if (values[0] + sum(i * v for i, v in enumerate(values[1:-1], 1))) % 103 != values[-1]:
        return None
    mode = {103:'A',104:'B',105:'C'}[values[0]]
    text = []
    shift = None
    for value in values[1:-1]:
        current = shift or mode
        shift = None
        if current == 'C' and value <= 99:
            text.append(f'{value:02d}')
        elif value <= 95:
            char = chr(value + 32) if current == 'B' or value < 64 else chr(value - 64)
            if ord(char) < 32:
                return None
            text.append(char)
        elif value == 99:
            mode = 'C'
        elif value == 100:
            if mode == 'B':  # FNC4 extended character set not supported.
                return None
            mode = 'B'
        elif value == 101:
            if mode == 'A':
                return None
            mode = 'A'
        elif value == 98 and mode in ('A', 'B'):
            shift = 'B' if mode == 'A' else 'A'
        elif value != 102:  # FNC1 separator is not part of the filename.
            return None
    result = ''.join(text).strip()
    return result if result else None


def read_line(line, y=0):
    changes = np.flatnonzero(np.r_[True, line[1:] != line[:-1], True])
    lengths = np.diff(changes)
    values_at = line[changes[:-1]]
    found = []
    starts=np.flatnonzero(values_at)
    starts=starts[starts+25<len(lengths)]
    if not len(starts):
        return found
    windows=np.lib.stride_tricks.sliding_window_view(lengths,6)[starts].astype(float)
    totals=windows.sum(axis=1)
    errors=np.mean((windows[:,None,:]*11/totals[:,None,None]-TABLE[None,103:106,:])**2,axis=2)
    quiet=np.where(starts==0,True,lengths[np.maximum(starts-1,0)]>=3*totals/11)
    starts=starts[(errors.min(axis=1)<=.22)&(totals>=8)&quiet]
    for start in starts:
        first = _symbol(lengths[start:start+6], start=True)
        if first is None:
            continue
        values = [first[0]]
        errors = [first[1]]
        pos = start+6
        module = sum(lengths[start:start+6]) / 11
        while pos+7 <= len(lengths) and len(values) < 160:
            stop = lengths[pos:pos+7].astype(float)
            stop_error = np.mean((stop * 13 / stop.sum() - np.array([2,3,3,1,1,1,2]))**2)
            quiet_end = pos+7 == len(lengths) or lengths[pos+7] >= 3*module
            if stop_error < 0.2 and len(values) >= 3 and quiet_end:
                value = _decode_values(values)
                if value:
                    # Require a quiet zone at both sides where available.
                    if start and lengths[start-1] < 3*module:
                        break
                    if pos+7 < len(lengths) and lengths[pos+7] < 3*module:
                        break
                    found.append(Barcode(value,(int(changes[start]),y,int(changes[pos+7]),y+1),
                                         1-min(1,float(np.mean(errors)))))
                break
            symbol = _symbol(lengths[pos:pos+6])
            if symbol is None or symbol[0] >= 103:
                break
            current_module = sum(lengths[pos:pos+6])/11
            if not 0.6 < current_module/module < 1.5:
                break
            values.append(symbol[0])
            errors.append(symbol[1])
            pos += 6
    return found


def read_barcodes(image, stride=6):
    gray = np.asarray(image.convert('L'))
    found = []
    for y in range(0, gray.shape[0], stride):
        line = gray[y] < 140
        if np.count_nonzero(line[1:] != line[:-1]) < 24:
            continue
        for candidate in read_line(line,y)+read_code39_line(line,y):
            x0, _, x1, _ = candidate.box
            existing = next((b for b in found if b.value == candidate.value and
                             abs(b.box[0]-x0)<8 and abs(b.box[2]-x1)<8 and
                             y-b.box[3] < stride*3), None)
            if existing:
                existing.box = (x0, existing.box[1], x1, y+1)
                existing.score = min(existing.score,candidate.score)
            else:
                found.append(candidate)
    return [b for b in found if b.box[3]-b.box[1] >= max(2,stride)]
