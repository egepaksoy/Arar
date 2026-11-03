"""Page analysis: Receiving Report barcode and stamps on the rendered page.

Every page is analysed as one image at its own resolution, whether the PDF is a
scan or composed from separate images, so no stamp or barcode template is
needed. Low confidence never becomes an automatic cover.
"""
import threading

import cv2
import numpy as np
import pypdfium2 as pdfium

from .barcodes import barcode_regions, decode_region
from .models import Evidence, PageResult
from .offline import local_path
from .report_ocr import strip_heading
from .stamps import find_stamps

PDF_LOCK = threading.RLock()  # PDFium is not safe for simultaneous thread calls.
SCAN_DPI_RANGE = (100, 300)   # Scans are analysed at their own resolution in this range.
COMPOSED_DPI = 200            # Pages built from text and placed images.
DEFAULT_THRESHOLDS = (.85, .74)  # stamp_threshold, scan_stamp_threshold defaults
UNREAD_REGULARITY = .75      # an unreadable region must look this much like bars to search its heading


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


def _analysis_scale(page):
    """Render scale and whether the page is a full-page scan.

    A scan is rendered at the resolution it was scanned at: enlarging it adds
    no detail but multiplies the work for every later step.
    """
    width,height=page.get_size()
    for obj in page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE]):
        left,bottom,right,top=obj.get_bounds()
        if right-left>width*.75 and top-bottom>height*.65:
            pixels=max(obj.get_px_size())
            dpi=pixels/max(right-left,top-bottom)*72
            return min(max(dpi,SCAN_DPI_RANGE[0]),SCAN_DPI_RANGE[1])/72,True
    return COMPOSED_DPI/72,False


def _load_analysis_page(source,index,cancel=None):
    """Copy the page image while locked; no PDFium handles escape into analysis."""
    with PDF_LOCK:
        if cancel is not None and cancel.is_set():
            return None
        with pdfium.PdfDocument(str(source)) as doc:
            page=doc[index]
            try:
                scale,scanned=_analysis_scale(page)
                bitmap=page.render(scale=scale)
                try:
                    image=np.asarray(bitmap.to_pil().convert('RGB'))
                finally:
                    bitmap.close()
                return image,scale,scanned
            finally:
                page.close()


def _strip(gray,box,below,depth):
    """Text band beside a barcode, turned upright: above it, or below it when reversed.

    depth is the band height as a share of the barcode height.
    """
    x0,y0,x1,y1=box
    width,height=x1-x0,max(y1-y0,30)
    left,right=max(0,int(x0-width*.05)),min(gray.shape[1],int(x1+width*.05))
    if below:
        top,bottom=y1-2,min(gray.shape[0],int(y1+height*depth))
        return gray[top:bottom,left:right][::-1,::-1],(left,top,right,bottom)
    top,bottom=max(0,int(y0-height*depth)),y0+2
    return gray[top:bottom,left:right],(left,top,right,bottom)


def _rotated_box(box,rotated,height):
    """Map a box from the 90-degree clockwise rotated page back to the page."""
    if not rotated:
        return box
    a,b,c,d=box
    return (b,height-1-c,d,height-1-a)


def _heading_beside(page,region,sides,enlarge):
    """Confidence and strip box of a RECEIVING REPORT NO heading next to a region."""
    # The heading sits right above the bars; a narrow band first keeps
    # unrelated lines (a label stuck over other text) out of the OCR.
    for below in sides:
        for depth in (.65,1.1):
            strip,strip_box=_strip(page,region,below,depth)
            strip=cv2.resize(strip,None,fx=enlarge,fy=enlarge,interpolation=cv2.INTER_CUBIC)
            confidence=strip_heading(strip)
            if confidence:
                return confidence,strip_box
    return 0.,None


def _stacked(upper,lower,reversed_):
    """Whether ``lower`` follows ``upper`` directly in reading direction (one label)."""
    if reversed_:
        upper,lower=(upper[0],-upper[3],upper[2],-upper[1]),(lower[0],-lower[3],lower[2],-lower[1])
    gap=lower[1]-upper[3]
    overlap=min(upper[2],lower[2])-max(upper[0],lower[0])
    # Codes printed on one label sit tight together; a separate label is further away.
    return 0<=gap<=.4*(upper[3]-upper[1]) and overlap>=.5*min(upper[2]-upper[0],lower[2]-lower[0])


def find_report_barcodes(gray,dpi,cancel=None):
    """Find Receiving Report barcodes by reading only the text next to each barcode.

    Returns (reports, others, headings, boxes): reports are (Barcode or None,
    heading confidence, page box) for barcodes under a RECEIVING REPORT NO
    heading, None meaning the bars could not be read; others are the remaining
    decoded values; headings are (page box, confidence) of the matched headings;
    boxes are all barcode regions. Barcodes stacked right under a headed one
    belong to the same heading, so a second code there is reported as well.
    """
    reports,others,headings,boxes=[],[],[],[]
    height=gray.shape[0]
    enlarge=max(1.,300/dpi)
    for rotated in (False,True):
        page=cv2.rotate(gray,cv2.ROTATE_90_CLOCKWISE) if rotated else gray
        read=[]
        for bars in barcode_regions(page,dpi):
            if cancel is not None and cancel.is_set():
                return [],[],[],[]
            boxes.append(_rotated_box(bars.box,rotated,height))
            found,reversed_=decode_region(page,bars.box,dpi)
            if not found and bars.regularity<UNREAD_REGULARITY:
                continue   # texture that is probably not a barcode at all
            # A reversed symbol is upside down, so its heading is below it.
            confidence,strip_box=_heading_beside(page,bars.box,(reversed_,) if found else (False,True),enlarge)
            read.append([bars.box,found,reversed_,confidence])
            if confidence:
                headings.append((_rotated_box(strip_box,rotated,height),confidence))
        for item in read:
            box,found,reversed_,confidence=item
            if confidence:
                continue
            under=next((other for other in read if other[3] and other[1] and other is not item
                        and _stacked(other[0],box,other[2])),None)
            if under is not None and found:
                item[3]=under[3]
        for box,found,reversed_,confidence in read:
            if not confidence:
                others.extend(b.value for b in found)
            elif found:
                reports.extend((b,confidence,_rotated_box(b.box,rotated,height)) for b in found)
            else:
                reports.append((None,confidence,_rotated_box(box,rotated,height)))
    return reports,others,headings,boxes


def analyze_page(result,cancel=None, *, stamp_threshold=.85, scan_stamp_threshold=.74,
                 review_missing_stamp=True, faint_blue_as_blue=False):
    source=local_path(result.source,must_exist=True)
    stat=source.stat()
    if result.source_signature and result.source_signature!=(stat.st_size,stat.st_mtime_ns):
        raise ValueError('Kaynak PDF değişmiş. Dosyayı kaldırıp yeniden ekleyin.')
    loaded=_load_analysis_page(source,result.index,cancel)
    if loaded is None:
        return result
    rgb,scale,scanned=loaded
    dpi=scale*72
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    reports,others,headings,boxes=find_report_barcodes(gray,dpi,cancel)
    if cancel is not None and cancel.is_set():
        return result
    # The accuracy settings keep their meaning: a lower value accepts weaker rings.
    threshold,default=(scan_stamp_threshold,DEFAULT_THRESHOLDS[1]) if scanned else (stamp_threshold,DEFAULT_THRESHOLDS[0])
    sensitivity=min(1.35,max(.55,threshold/default))
    stamps=find_stamps(rgb,dpi,exclude=boxes,faint_blue_as_blue=faint_blue_as_blue,
                       sensitivity=sensitivity,cancel=cancel)
    if cancel is not None and cancel.is_set():
        return result
    points=lambda box:tuple(float(v)/scale for v in box)
    # A stamp's confidence is the highest accuracy setting (0-1) that still
    # keeps it, so the value shown on the preview can be compared directly
    # with the setting used for this kind of page.
    evidence=[Evidence(s.kind,points(s.box),min(.99,s.strength*default),
                       'Yuvarlak mühür'+(' (soluk mavi)' if s.pale_blue else '')) for s in stamps]
    heading_evidence=[Evidence('heading',points(box),confidence,'OCR: RECEIVING REPORT NO')
                      for box,confidence in headings]
    targets=[(b.value,points(box),min(confidence,b.score),b.kind+' / OCR başlığı')
             for b,confidence,box in reports if b is not None]
    unreadable_heading=any(b is None for b,_,_ in reports)
    unique=list(dict.fromkeys(t[0] for t in targets))
    result.other_barcodes=list(dict.fromkeys(v for v in others if v not in unique))
    result.target_found=bool(reports)
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
    elif unreadable_heading and not targets:
        result.state,result.reason='review','Receiving Report No yazısı bulundu ancak altındaki barkod okunamadı. Kullanıcı kararı gerekli.'
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
    else:
        result.state,result.reason='attachment','Receiving Report barkodu bulunmadı; devam sayfası adayı.'
    return result
