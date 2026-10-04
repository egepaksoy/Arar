"""Lossless page copying to local PDFs, with collision-safe atomic writes."""
from pathlib import Path
from contextlib import ExitStack
import json
import re
import uuid
from datetime import datetime
from pypdf import PdfReader, PdfWriter
from .offline import local_path


def safe_filename(number):
    name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',number).strip(' .')[:100]
    if not name:
        raise ValueError('Belge numarası boş olamaz.')
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
        name='_'+name
    return name


def _claim(folder,stem,suffix):
    index=1
    while True:
        name=stem if index==1 else f'{stem}_{index:02d}'
        path=folder/(name+suffix)
        try:
            handle=path.open('xb')
            handle.close()
            return path
        except FileExistsError:
            index+=1


def export_groups(groups,output_dir):
    if not groups:
        raise ValueError('Kaydedilecek belge yok.')
    folder=local_path(output_dir)
    folder.mkdir(parents=True,exist_ok=True)
    created=[]
    temporary=[]
    manifest=[]
    try:
        with ExitStack() as stack:
            readers={}
            for group in groups:
                if not group.pages or not group.number:
                    raise ValueError('Her belgenin kapak numarası ve sayfaları olmalı.')
                writer=PdfWriter()
                for page in group.pages:
                    source=local_path(page.source,must_exist=True)
                    stat=source.stat()
                    if page.source_signature and page.source_signature!=(stat.st_size,stat.st_mtime_ns):
                        raise ValueError('Kaynak PDF analizden sonra değişmiş. Dosyayı yeniden ekleyin: '+source.name)
                    if str(source) not in readers:
                        readers[str(source)]=PdfReader(stack.enter_context(source.open('rb')))
                    reader=readers[str(source)]
                    if reader.is_encrypted:
                        raise ValueError('Şifreli PDF dışa aktarılamaz.')
                    writer.add_page(reader.pages[page.index])
                target=_claim(folder,safe_filename(group.number),'.pdf')
                created.append(target)
                temp=folder/('.arar-'+uuid.uuid4().hex+'.tmp')
                temporary.append(temp)
                with temp.open('xb') as handle:
                    writer.write(handle)
                # Validate count before replacing our exclusive reservation.
                with temp.open('rb') as handle:
                    if len(PdfReader(handle).pages)!=len(group.pages):
                        raise ValueError('Oluşturulan PDF sayfa sayısı doğrulanamadı.')
                temp.replace(target)
                manifest.append({'dosya':target.name,'barkod':group.number,
                                 'sayfalar':[{'kaynak':p.source,'sayfa':p.index+1,
                                              'karar':p.effective_state,'manuel':bool(p.decision),
                                              'muhur':p.stamp} for p in group.pages]})
            report=_claim(folder,'Arar_islem_raporu','.json')
            created.append(report)
            temp=folder/('.arar-'+uuid.uuid4().hex+'.tmp')
            temporary.append(temp)
            temp.write_text(json.dumps({'tarih':datetime.now().astimezone().isoformat(),
                                        'belgeler':manifest},ensure_ascii=False,indent=2),encoding='utf-8')
            temp.replace(report)
        return created
    except Exception:
        # Roll back only files exclusively reserved by this batch.
        for path in temporary+created:
            path.unlink(missing_ok=True)
        raise
