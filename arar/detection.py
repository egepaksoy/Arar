"""Local image matching. Low confidence never becomes an automatic cover."""
from pathlib import Path
import threading
from functools import lru_cache
import numpy as np
import cv2
from PIL import Image, ImageOps
import pypdfium2 as pdfium
from .barcodes import read_barcodes
from .models import Evidence, PageResult, ROOT
from .offline import local_path
from .report_ocr import find_report_headings

PDF_LOCK = threading.RLock()  # PDFium is not safe for simultaneous thread calls.
ASSETS = ROOT / 'assets'


def _ink(image):
    return (255-np.asarray(image.convert('L'),dtype=float))/255


def _tight(image):
    arr = np.asarray(image.convert('L'))
    ys,xs = np.where(arr<235)
    if len(xs)<10:
        return None
    return image.crop((int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)))


def _similarity(first,second):
    a,b = _tight(first),_tight(second)
    if a is None or b is None:
        return 0.
    if abs(np.log((a.width/a.height)/(b.width/b.height))) > .28:
        return 0.
    va = _ink(a.resize((200,32),Image.Resampling.BILINEAR)).ravel()
    vb = _ink(b.resize((200,32),Image.Resampling.BILINEAR)).ravel()
    va -= va.mean()
    vb -= vb.mean()
    norm = np.linalg.norm(va)*np.linalg.norm(vb)
    return float(np.dot(va,vb)/norm) if norm>0 else 0.


HEADER = Image.open(ASSETS/'receiving_report.png').convert('RGB').crop((90,0,715,49))
STAMP_TEMPLATES = [(kind,Image.open(ASSETS/name).convert('RGB')) for kind,name in (
    ('blue','stamp_blue_1.png'),('blue','stamp_blue_2.png'),('blue','stamp_blue_3.png'),('blue','stamp_blue_4.png'),('blue','stamp_blue_5.png'),
    ('faint','stamp_faint.png'),('black','stamp_black.png'))]


def heading_score(image,barcode):
    x0,y0,x1,_ = barcode.box
    width=x1-x0
    crop=image.crop((max(0,x0-2),max(0,int(y0-width*.09)),min(image.width,x1+2),
                     max(1,int(y0-width*.015))))
    score=_similarity(crop,HEADER)
    if score<.8:
        # Scanner paper tint and compression speckles must not define the
        # heading's ink bounds. Keep the original comparison for clean PDFs.
        clean=crop.convert('L').point(lambda value: 0 if value<180 else 255)
        reference=HEADER.convert('L').point(lambda value: 0 if value<180 else 255)
        score=max(score,_similarity(clean,reference))
    return score


def _barcodes_below_heading(image, heading, cancel=None):
    """Try the immediate block, then a wider/deeper block; keep ambiguities."""
    from .barcodes import Barcode
    x0,y0,x1,y1=heading.box
    width,height=x1-x0,y1-y0
    for margin,span,depth in ((.08,1.9,5),(.18,None,12)):
        if cancel is not None and cancel.is_set():
            return []
        left=max(0,int(x0-width*margin))
        top=max(0,int(y1-height*.25))
        right=image.width if span is None else min(image.width,round(x0+width*span))
        bottom=min(image.height,round(y1+height*depth))
        if right<=left or bottom<=top:
            continue
        crop=image.crop((left,top,right,bottom))
        found=[]
        # Local contrast helps pale scans without changing the barcode decoder.
        for candidate_image in (crop,ImageOps.autocontrast(crop.convert('L'))):
            for barcode in read_barcodes(candidate_image,stride=2):
                a,b,c,d=barcode.box
                box=(a+left,b+top,c+left,d+top)
                overlap=max(0,min(box[2],x1)-max(box[0],x0))
                # A nearby PART NO barcode must not inherit this heading.
                if (abs(box[0]-x0)>max(height*2,width*.18)
                        or overlap<width*.55 or box[1]<y1-height*.5):
                    continue
                found.append(Barcode(barcode.value,box,barcode.score,barcode.kind))
            if found:
                break
        if found:
            return found
    return []


def _stamp_match(image):
    if not .55 < image.width/image.height < 1.7:
        return None
    return max(((kind,_similarity(image,template)) for kind,template in STAMP_TEMPLATES),
               key=lambda item:item[1])


def _classify_color(image, *, faint_blue_as_blue=False):
    rgb=np.asarray(image.convert('RGB'),dtype=float)
    dark=rgb.min(axis=2)<240
    blue=(rgb[:,:,2]-rgb[:,:,0]>18)&(rgb[:,:,2]-rgb[:,:,1]>4)&dark
    if dark.sum()>=20 and blue.sum()/dark.sum()>.3:
        # Preserve the usual saturation requirement unless explicitly enabled.
        saturation=(rgb.max(axis=2)-rgb.min(axis=2))[blue]
        return 'blue' if faint_blue_as_blue or float(np.percentile(saturation,75))>75 else 'faint'
    if faint_blue_as_blue:
        # Washed-out blue can fall below the normal color/brightness limits.
        # Require a blue bias across the ink, rather than a few tinted pixels.
        pale_ink=rgb.min(axis=2)<248
        pale_blue=(rgb[:,:,2]-rgb[:,:,0]>8)&(rgb[:,:,2]-rgb[:,:,1]>2)&pale_ink
        if pale_blue.sum()>=20 and pale_blue.sum()/pale_ink.sum()>.3:
            return 'blue'
    return 'black' if dark.sum()>=20 else 'none'


def _color_stamps(full, cancel=None, *, faint_blue_as_blue=False):
    """Blue stamp-sized ink blobs on a raster page, independent of templates.

    Scans wash out stamp ink and tint the paper, so shape templates score low
    even on a clear stamp. Ink is measured as blue excess over the paper tint,
    and handwriting is rejected by shape (long and sparse).
    """
    scale=min(1.,840/full.width)
    size=(max(1,round(full.width*scale)),max(1,round(full.height*scale)))
    rgb=cv2.resize(np.asarray(full),size,interpolation=cv2.INTER_AREA).astype(np.float32)
    chroma=rgb[:,:,2]-rgb[:,:,0]
    excess=chroma-float(np.median(chroma))
    mask=((excess>28)&(rgb.mean(axis=2)<236)).astype(np.uint8)
    joined=cv2.dilate(mask,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7)))
    count,labels,stats,_=cv2.connectedComponentsWithStats(joined,connectivity=8)
    page_width=size[0]
    findings=[]
    for index in range(1,count):
        if cancel is not None and cancel.is_set():
            return findings
        x,y,width,height,_=stats[index]
        if not .03*page_width<=width<=.3*page_width or not .6<=width/height<=1.8:
            continue
        ink=(labels[y:y+height,x:x+width]==index)&(mask[y:y+height,x:x+width]>0)
        if ink.sum()<250*(page_width/840)**2 or not .08<=ink.sum()/(width*height)<=.5:
            continue
        strength=float(np.percentile(excess[y:y+height,x:x+width][ink],75))
        kind='blue' if faint_blue_as_blue or strength>=42 else 'faint'
        box=tuple(v/scale/4 for v in (x,y,x+width,y+height))
        findings.append(Evidence(kind,box,min(.95,max(.5,strength/60)),'Renk tabanlı mühür bölgesi'))
    return findings


def _inside(box,outer):
    return (outer[0]<=(box[0]+box[2])/2<=outer[2]
            and outer[1]<=(box[1]+box[3])/2<=outer[3])


def _box_pdf(bounds,height):
    left,bottom,right,top=bounds
    return (left,height-top,right,height-bottom)


def _map_box(box,bounds,size,height):
    left,top,right,bottom=_box_pdf(bounds,height)
    sx,sy=(right-left)/size[0],(bottom-top)/size[1]
    return (left+box[0]*sx,top+box[1]*sy,left+box[2]*sx,top+box[3]*sy)


class _PreparedTemplate:
    def __init__(self, array):
        self.shape=array.shape
        self.centered=array-array.mean()
        self.norm=np.linalg.norm(self.centered)
        self.centered.setflags(write=False)
        self.pixels=np.ascontiguousarray(self.centered,dtype=np.float32)
        self.pixels.setflags(write=False)


class _PageCorrelation:
    """Page-local data; released after scanning, never retains previous pages."""
    def __init__(self, array):
        self.array=array
        self.shape=array.shape
        self.pixels=np.ascontiguousarray(array,dtype=np.float32)
        self.integral=np.pad(array,((1,0),(1,0))).cumsum(0).cumsum(1)
        self.squared=np.pad(array*array,((1,0),(1,0))).cumsum(0).cumsum(1)

    def variance(self,h,w):
        def window(integral):
            return integral[h:,w:]-integral[:-h,w:]-integral[h:,:-w]+integral[:-h,:-w]
        sums=window(self.integral)
        return window(self.squared)-sums*sums/(h*w)


@lru_cache(maxsize=1)
def _prepared_scan_templates():
    """Immutable, small template data shared by all page scans."""
    prepared=[]
    for _,template in STAMP_TEMPLATES:
        tight=_tight(template)
        for width in (24,28,32,36,42,46,50,54,58,64,70):
            height=max(16,round(width*tight.height/tight.width))
            array=_ink(tight.resize((width,height),Image.Resampling.BILINEAR))
            prepared.append(_PreparedTemplate(array))
    return tuple(prepared)


def _template_peak(array,template):
    """Full-page OpenCV search; re-score the peak in double precision."""
    h,w=template.shape
    if array.shape[0]<h or array.shape[1]<w:
        return 0.,(0,0)
    page=array if isinstance(array,_PageCorrelation) else _PageCorrelation(array)
    template=template if isinstance(template,_PreparedTemplate) else _PreparedTemplate(template)
    if template.norm<1e-6:
        return 0.,(0,0)
    scores=cv2.matchTemplate(page.pixels,template.pixels,cv2.TM_CCOEFF_NORMED)
    # Float32 FFT roundoff can give empty windows a spurious score near 1.
    # 1e-8 is below the variance of even one changed 8-bit pixel (~1.5e-5).
    scores[page.variance(h,w)<=max(1e-8,1e-12/template.norm**2)]=0.
    _,_,_,(x,y)=cv2.minMaxLoc(scores)
    # OpenCV uses float32 to find the location. Preserve threshold precision
    # with the same normalized correlation on the original float64 pixels.
    crop=page.array[y:y+h,x:x+w]
    centered=crop-crop.mean()
    denom=np.linalg.norm(centered)*template.norm
    score=float(np.sum(centered*template.centered)/denom) if denom>1e-6 else 0.
    return score,(x,y)


def _scan_stamps(image,scale, cancel=None, *, min_score=.74, faint_blue_as_blue=False):
    # This fallback handles raster scans. Templates come from the supplied
    # examples, so uncertain or novel shapes remain subject to user review.
    if cancel is not None and cancel.is_set():
        return []
    gray=_PageCorrelation(_ink(image))
    findings=[]
    for template in _prepared_scan_templates():
        height,width=template.shape
        if cancel is not None and cancel.is_set():
            return findings
        score,(x,y)=_template_peak(gray,template)
        if score<min_score:
            continue
        crop=image.crop((x,y,x+width,y+height))
        kind=_classify_color(crop,faint_blue_as_blue=faint_blue_as_blue)
        if kind=='none':
            continue
        box=(x/scale,y/scale,(x+width)/scale,(y+height)/scale)
        duplicate=next((f for f in findings if abs(f.box[0]-box[0])<12
                        and abs(f.box[1]-box[1])<12),None)
        if duplicate is None or score>duplicate.confidence:
            if duplicate is not None:
                findings.remove(duplicate)
            findings.append(Evidence(kind,box,score,'Görsel şablon eşleşmesi'))
    return findings


def render_page(source,index,max_size=(850,1100)):
    source=local_path(source,must_exist=True)
    with PDF_LOCK, pdfium.PdfDocument(str(source)) as doc:
        page=doc[index]
        try:
            scale=min(max_size[0]/page.get_width(),max_size[1]/page.get_height())
            bitmap=page.render(scale=scale)
            try:
                return bitmap.to_pil().convert('RGB'),page.get_size()
            finally:
                bitmap.close()
        finally:
            page.close()


def list_pages(source):
    source=local_path(source,must_exist=True)
    if source.suffix.lower()!='.pdf':
        raise ValueError('Bu sürüm PDF dosyalarını kabul eder.')
    stat=source.stat()
    signature=(stat.st_size,stat.st_mtime_ns)
    with PDF_LOCK, pdfium.PdfDocument(str(source)) as doc:
        if len(doc)>5000:
            raise ValueError('Tek dosyada en fazla 5000 sayfa desteklenir.')
        return [PageResult(str(source),i,source_signature=signature) for i in range(len(doc))]


def _load_analysis_page(source,index,cancel=None):
    """Copy PDF data while locked; no PDFium handles escape into image analysis."""
    with PDF_LOCK:
        if cancel is not None and cancel.is_set():
            return None
        with pdfium.PdfDocument(str(source)) as doc:
            page=doc[index]
            try:
                width,height=page.get_size()
                bitmap=page.render(scale=4)
                try:
                    full=bitmap.to_pil().convert('RGB')
                finally:
                    bitmap.close()
                embedded=[]
                fallback=False
                for obj in page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE]):
                    if cancel is not None and cancel.is_set():
                        return None
                    size=obj.get_px_size()
                    bounds=obj.get_bounds()
                    if size[0]<40 or size[1]<20:
                        continue
                    if (size[0]*size[1]>12_000_000 or
                            (bounds[2]-bounds[0]>width*.75 and bounds[3]-bounds[1]>height*.65)):
                        # Full-page scans are already in full; avoid decoding them twice.
                        fallback=True
                        continue
                    bitmap=obj.get_bitmap()
                    try:
                        embedded.append((bitmap.to_pil().convert('RGB'),bounds))
                    finally:
                        bitmap.close()
                return full,height,embedded,fallback
            finally:
                page.close()


def analyze_page(result,cancel=None, *, stamp_threshold=.85, scan_stamp_threshold=.74,
                 review_other_barcodes=True, review_missing_stamp=True, faint_blue_as_blue=False):
    evidence=[]
    targets=[]
    others=[]
    fallback=False
    heading_evidence=[]
    unreadable_heading=False
    source=local_path(result.source,must_exist=True)
    stat=source.stat()
    if result.source_signature and result.source_signature!=(stat.st_size,stat.st_mtime_ns):
        raise ValueError('Kaynak PDF değişmiş. Dosyayı kaldırıp yeniden ekleyin.')
    loaded=_load_analysis_page(source,result.index,cancel)
    if loaded is None:
        return result
    full,height,embedded,fallback=loaded
    rotation,headings=find_report_headings(full,cancel)
    if cancel is not None and cancel.is_set():
        return result
    if headings:
        oriented=full.rotate(rotation,expand=True)
        for heading in headings:
            mapped=_unrotate_box(heading.box,rotation,full.size)
            heading_evidence.append(Evidence('heading',tuple(v/4 for v in mapped),
                                             heading.confidence,'OCR: RECEIVING REPORT NO'))
            bars=_barcodes_below_heading(oriented,heading,cancel)
            if not bars:
                unreadable_heading=True
            for b in bars:
                box=_unrotate_box(b.box,rotation,full.size)
                targets.append((b.value,tuple(v/4 for v in box),
                                min(heading.confidence,b.score),b.kind+' / OCR başlığı'))
        # Preserve information about other codes without using them as
        # report targets or requiring an image match for OCR results.
        others.extend(b.value for b in read_barcodes(oriented,stride=12))
    for im,bounds in embedded:
        if cancel is not None and cancel.is_set():
            return result
        if not headings and im.width/im.height>2.5:
            for b in read_barcodes(im,stride=2):
                score=heading_score(im,b)
                box=_map_box(b.box,bounds,im.size,height)
                if score>=.8:
                    targets.append((b.value,box,min(score,b.score),b.kind))
                else:
                    others.append(b.value)
        stamp=_stamp_match(im)
        if stamp and stamp[1]>=stamp_threshold:
            kind=_classify_color(im,faint_blue_as_blue=faint_blue_as_blue)
            evidence.append(Evidence(kind,_box_pdf(bounds,height),stamp[1],
                                     'Örnek mühür ile görsel eşleşme'))
    if not targets or fallback:
        # 288 dpi retains narrow bars. Try four cardinal orientations.
        for rotation in (() if headings else (0,90,180,270)):
            if cancel is not None and cancel.is_set():
                return result
            oriented=full.rotate(rotation,expand=True)
            bars=read_barcodes(oriented,stride=12)
            for b in bars:
                score=heading_score(oriented,b)
                if score>=.8:
                    # Map displayed crop back into original PDF coordinates.
                    box=_unrotate_box(b.box,rotation,full.size)
                    targets.append((b.value,tuple(v/4 for v in box),min(score,b.score),b.kind))
                else:
                    others.append(b.value)
            if targets:
                break
        if fallback or (result.index==0 and not targets and not evidence):
            small=full.resize((round(full.width/4*1.25),round(full.height/4*1.25)))
            colored=_color_stamps(full,cancel,faint_blue_as_blue=faint_blue_as_blue)
            scanned=_scan_stamps(small,1.25,cancel,min_score=scan_stamp_threshold,
                                 faint_blue_as_blue=faint_blue_as_blue)
            evidence.extend(colored)
            evidence.extend(f for f in scanned
                            if not any(_inside(f.box,c.box) for c in colored))
    # Deduplicate observations without choosing among different target numbers.
    if cancel is not None and cancel.is_set():
        return result
    unique=list(dict.fromkeys(t[0] for t in targets))
    result.other_barcodes=list(dict.fromkeys(v for v in others if v not in unique))
    result.target_found=bool(targets or headings)
    result.barcode=unique[0] if len(unique)==1 else ''
    result.evidence=evidence+heading_evidence+[Evidence('barcode',b,s,k+': '+v) for v,b,s,k in targets]
    kinds={f.kind for f in evidence}
    result.stamp='mixed' if 'blue' in kinds and ('black' in kinds or 'faint' in kinds) else (
        'black' if 'black' in kinds else 'faint' if 'faint' in kinds else 'blue' if 'blue' in kinds else 'none')
    result.first_page_error=result.index==0 and not result.target_found and result.stamp=='none'
    if result.first_page_error:
        result.state,result.reason='review','İlk sayfada Receiving Report No ve herhangi bir mühür bulunamadı. Dosyayı kontrol edin.'
    elif len(unique)>1:
        result.state,result.reason='review','Birden fazla Receiving Report numarası var. Kapak numarasını belirleyin.'
    elif unreadable_heading:
        result.state,result.reason='review','Receiving Report No yazısı bulundu ancak altındaki barkod genişletilmiş aramada da okunamadı. Kullanıcı kararı gerekli.'
    elif targets and not result.barcode:
        result.state,result.reason='review','Receiving Report barkodu okunamadı.'
    elif targets and result.stamp=='blue':
        result.state,result.reason='cover','Receiving Report barkodu ve yalnızca mavi mühür bulundu.'
    elif targets and result.stamp=='none' and not review_missing_stamp:
        result.state,result.reason='attachment','Receiving Report bulundu ancak mühür bulunamadı; ayar gereği devam sayfası adayı.'
    elif targets:
        reasons={'mixed':'Mavi ve siyah/soluk mühür birlikte bulundu.',
                 'black':'Siyah mühür bulundu. Otomatik kapak olamaz.',
                 'faint':'Soluk/renksiz mühür bulundu. Otomatik kapak olamaz.',
                 'none':'Uygun mühür güvenle bulunamadı.'}
        result.state,result.reason='review',reasons[result.stamp]+' Kullanıcı kararı gerekli.'
    elif result.other_barcodes and review_other_barcodes:
        result.state,result.reason='review','Başka barkodlar bulundu; Receiving Report başlığı doğrulanamadı.'
    else:
        result.state,result.reason='attachment','Receiving Report barkodu bulunmadı; devam sayfası adayı.'
    return result


def _unrotate_box(box,rotation,size):
    width,height=size
    points=[(box[0],box[1]),(box[2],box[1]),(box[0],box[3]),(box[2],box[3])]
    if rotation==90:
        points=[(width-y,x) for x,y in points]
    elif rotation==180:
        points=[(width-x,height-y) for x,y in points]
    elif rotation==270:
        points=[(y,height-x) for x,y in points]
    xs,ys=zip(*points)
    return min(xs),min(ys),max(xs),max(ys)
