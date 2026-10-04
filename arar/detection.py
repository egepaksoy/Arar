"""Local image matching. Low confidence never becomes an automatic cover."""
from pathlib import Path
import threading
import numpy as np
from PIL import Image, ImageOps
import pypdfium2 as pdfium
from .barcodes import read_barcodes
from .models import Evidence, PageResult, ROOT
from .offline import local_path

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
    ('blue','stamp_blue_1.png'),('blue','stamp_blue_2.png'),
    ('faint','stamp_faint.png'),('black','stamp_black.png'))]


def heading_score(image,barcode):
    x0,y0,x1,_ = barcode.box
    width=x1-x0
    crop=image.crop((max(0,x0-2),max(0,int(y0-width*.09)),min(image.width,x1+2),
                     max(1,int(y0-width*.015))))
    return _similarity(crop,HEADER)


def _stamp_match(image):
    if not .55 < image.width/image.height < 1.7:
        return None
    return max(((kind,_similarity(image,template)) for kind,template in STAMP_TEMPLATES),
               key=lambda item:item[1])


def _classify_color(image):
    rgb=np.asarray(image.convert('RGB'),dtype=float)
    dark=rgb.min(axis=2)<240
    blue=(rgb[:,:,2]-rgb[:,:,0]>18)&(rgb[:,:,2]-rgb[:,:,1]>4)&dark
    if dark.sum()<20:
        return 'none'
    if blue.sum()/dark.sum()>.3:
        # Faint purple ink must not be treated as an eligible blue stamp.
        saturation=(rgb.max(axis=2)-rgb.min(axis=2))[blue]
        return 'blue' if float(np.percentile(saturation,75))>75 else 'faint'
    return 'black'


def _box_pdf(bounds,height):
    left,bottom,right,top=bounds
    return (left,height-top,right,height-bottom)


def _map_box(box,bounds,size,height):
    left,top,right,bottom=_box_pdf(bounds,height)
    sx,sy=(right-left)/size[0],(bottom-top)/size[1]
    return (left+box[0]*sx,top+box[1]*sy,left+box[2]*sx,top+box[3]*sy)


def _sum_window(array,h,w):
    integral=np.pad(array,((1,0),(1,0))).cumsum(0).cumsum(1)
    return integral[h:,w:]-integral[:-h,w:]-integral[h:,:-w]+integral[:-h,:-w]


def _template_peak(array,template):
    """Normalized correlation through FFT, using only bundled NumPy."""
    h,w=template.shape
    if array.shape[0]<h or array.shape[1]<w:
        return 0.,(0,0)
    centered=template-template.mean()
    norm=np.linalg.norm(centered)
    if norm<1e-6:
        return 0.,(0,0)
    shape=(array.shape[0]+h-1,array.shape[1]+w-1)
    # Power-of-two transforms are faster than arbitrary dimensions.
    shape=tuple(1<<(n-1).bit_length() for n in shape)
    corr=np.fft.irfft2(np.fft.rfft2(array,s=shape)*
                       np.fft.rfft2(centered[::-1,::-1],s=shape),s=shape)
    corr=corr[h-1:array.shape[0],w-1:array.shape[1]]
    sums=_sum_window(array,h,w)
    squares=_sum_window(array*array,h,w)
    denom=np.sqrt(np.maximum(0,squares-sums*sums/(h*w)))*norm
    scores=np.divide(corr,denom,out=np.zeros_like(corr),where=denom>1e-6)
    y,x=np.unravel_index(np.argmax(scores),scores.shape)
    return float(scores[y,x]),(int(x),int(y))


def _scan_stamps(image,scale, cancel=None):
    # This fallback handles raster scans. Templates come from the supplied
    # examples, so uncertain or novel shapes remain subject to user review.
    gray=_ink(image)
    findings=[]
    for _,template in STAMP_TEMPLATES:
        tight=_tight(template)
        for width in (24,32,42,54,70):
            if cancel is not None and cancel.is_set():
                return findings
            height=max(16,round(width*tight.height/tight.width))
            temp=_ink(tight.resize((width,height),Image.Resampling.BILINEAR))
            score,(x,y)=_template_peak(gray,temp)
            if score<.74:
                continue
            crop=image.crop((x,y,x+width,y+height))
            kind=_classify_color(crop)
            if kind=='none':
                continue
            box=(x/scale,y/scale,(x+width)/scale,(y+height)/scale)
            if not any(abs(f.box[0]-box[0])<12 and abs(f.box[1]-box[1])<12 for f in findings):
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


def analyze_page(result,cancel=None):
    evidence=[]
    targets=[]
    others=[]
    fallback=False
    source=local_path(result.source,must_exist=True)
    stat=source.stat()
    if result.source_signature and result.source_signature!=(stat.st_size,stat.st_mtime_ns):
        raise ValueError('Kaynak PDF değişmiş. Dosyayı kaldırıp yeniden ekleyin.')
    with PDF_LOCK, pdfium.PdfDocument(str(source)) as doc:
        page=doc[result.index]
        try:
            height=page.get_height()
            for obj in page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE]):
                if cancel is not None and cancel.is_set():
                    return result
                size=obj.get_px_size()
                bounds=obj.get_bounds()
                if size[0]<40 or size[1]<20:
                    continue
                if size[0]*size[1]>12_000_000:
                    fallback=True
                    continue
                bitmap=obj.get_bitmap()
                try:
                    im=bitmap.to_pil().convert('RGB')
                finally:
                    bitmap.close()
                # Large full-page images need page-space detection, rotation
                # handling, and scan templates rather than individual objects.
                if bounds[2]-bounds[0]>page.get_width()*.75 and bounds[3]-bounds[1]>height*.65:
                    fallback=True
                    continue
                if im.width/im.height>2.5:
                    for b in read_barcodes(im,stride=2):
                        score=heading_score(im,b)
                        box=_map_box(b.box,bounds,im.size,height)
                        if score>=.8:
                            targets.append((b.value,box,min(score,b.score),b.kind))
                        else:
                            others.append(b.value)
                stamp=_stamp_match(im)
                if stamp and stamp[1]>=.85:
                    kind=_classify_color(im)
                    evidence.append(Evidence(kind,_box_pdf(bounds,height),stamp[1],
                                             'Örnek mühür ile görsel eşleşme'))
            if not targets or fallback:
                # 288 dpi retains narrow bars. Try four cardinal orientations.
                bitmap=page.render(scale=4)
                try:
                    full=bitmap.to_pil().convert('RGB')
                finally:
                    bitmap.close()
                for rotation in (0,90,180,270):
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
                if targets and fallback:
                    small=full.resize((round(full.width/4*1.25),round(full.height/4*1.25)))
                    evidence.extend(_scan_stamps(small,1.25,cancel))
        finally:
            page.close()
    # Deduplicate observations without choosing among different target numbers.
    unique=list(dict.fromkeys(t[0] for t in targets))
    result.other_barcodes=list(dict.fromkeys(others))
    result.target_found=bool(targets)
    result.barcode=unique[0] if len(unique)==1 else ''
    result.evidence=evidence+[Evidence('barcode',b,s,k+': '+v) for v,b,s,k in targets]
    kinds={f.kind for f in evidence}
    result.stamp='mixed' if 'blue' in kinds and ('black' in kinds or 'faint' in kinds) else (
        'black' if 'black' in kinds else 'faint' if 'faint' in kinds else 'blue' if 'blue' in kinds else 'none')
    if len(unique)>1:
        result.state,result.reason='review','Birden fazla Receiving Report numarası var. Kapak numarasını belirleyin.'
    elif targets and not result.barcode:
        result.state,result.reason='review','Receiving Report barkodu okunamadı.'
    elif targets and result.stamp=='blue':
        # Even exact positive matches cannot rule out a novel additional black
        # stamp. Scanned pages therefore require an explicit confirmation.
        if fallback:
            result.state,result.reason='review','Taranmış sayfada mavi mühür adayı. Diğer mühürleri kontrol edip onaylayın.'
        else:
            result.state,result.reason='cover','Receiving Report barkodu ve örneklerle eşleşen mavi mühür bulundu.'
    elif targets:
        reasons={'mixed':'Mavi ve siyah/soluk mühür birlikte bulundu.',
                 'black':'Siyah mühür bulundu. Otomatik kapak olamaz.',
                 'faint':'Soluk/renksiz mühür bulundu. Otomatik kapak olamaz.',
                 'none':'Uygun mühür güvenle bulunamadı.'}
        result.state,result.reason='review',reasons[result.stamp]+' Kullanıcı kararı gerekli.'
    elif result.other_barcodes:
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
