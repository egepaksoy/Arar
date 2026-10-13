from dataclasses import dataclass, field, asdict
from pathlib import Path
import json
from .offline import local_path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    grouping: str = 'shared'
    rules_version: int = 2
    pause_on_later_barcode: bool = False
    output_dir: str = str(ROOT / 'Çıktı')
    confirm_cover: bool = True
    notify_analysis_done: bool = True
    stamp_threshold: int = 85
    scan_stamp_threshold: int = 74
    review_other_barcodes: bool = True
    review_missing_stamp: bool = True
    review_initial_mixed: bool = True
    review_initial_plain: bool = True
    review_later_mixed: bool = False
    review_later_plain: bool = False
    examples_dir: str = ''

    @classmethod
    def load(cls):
        try:
            data = json.loads((ROOT / '.arar' / 'settings.json').read_text(encoding='utf-8'))
            settings = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            # The updated rules share following documents between adjacent
            # blue covers. Migrate old preferences once; later choices persist.
            if data.get('rules_version') != 2:
                settings.grouping = 'shared'
                settings.rules_version = 2
            if settings.grouping not in ('shared', 'sequential'):
                settings.grouping = 'shared'
            settings.pause_on_later_barcode = bool(settings.pause_on_later_barcode)
            settings.confirm_cover = bool(settings.confirm_cover)
            settings.notify_analysis_done = bool(settings.notify_analysis_done)
            settings.review_other_barcodes = bool(settings.review_other_barcodes)
            settings.review_missing_stamp = bool(settings.review_missing_stamp)
            for name in ('review_initial_mixed','review_initial_plain','review_later_mixed','review_later_plain'):
                setattr(settings,name,bool(getattr(settings,name)))
            try:
                settings.examples_dir = str(local_path(settings.examples_dir)) if settings.examples_dir else ''
            except (OSError, ValueError, TypeError):
                settings.examples_dir = ''
            for name in ('stamp_threshold', 'scan_stamp_threshold'):
                value = getattr(settings, name)
                if type(value) is not int or not 50 <= value <= 99:
                    setattr(settings, name, cls.__dataclass_fields__[name].default)
            settings.output_dir = str(local_path(settings.output_dir))
            return settings
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self):
        for name in ('stamp_threshold', 'scan_stamp_threshold'):
            value = getattr(self, name)
            if type(value) is not int or not 50 <= value <= 99:
                raise ValueError('Mühür eşleşme eşikleri 50–99 arasında tam sayı olmalıdır.')
        local_path(self.output_dir)
        if self.examples_dir:
            local_path(self.examples_dir)
        folder = ROOT / '.arar'
        folder.mkdir(exist_ok=True)
        target = folder / 'settings.json'
        temp = folder / 'settings.tmp'
        temp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(target)


@dataclass
class Evidence:
    kind: str
    box: tuple[float, float, float, float]
    confidence: float
    detail: str = ''


@dataclass
class PageResult:
    source: str
    index: int
    barcode: str = ''
    target_found: bool = False
    stamp: str = 'none'
    state: str = 'pending'  # pending, cover, attachment, review
    reason: str = 'Henüz incelenmedi.'
    evidence: list[Evidence] = field(default_factory=list)
    decision: str = ''  # cover, attachment, or empty (automatic)
    manual_barcode: str = ''
    other_barcodes: list[str] = field(default_factory=list)
    source_signature: tuple[int,int] | None = None
    first_page_error: bool = False

    @property
    def number(self):
        return self.manual_barcode.strip() or self.barcode

    @property
    def effective_state(self):
        return self.decision or self.state

    def apply_analysis(self, result):
        """Apply a worker result on the UI thread, retaining manual choices."""
        if (self.source,self.index)!=(result.source,result.index):
            raise ValueError('Analiz sonucu farklı bir sayfaya ait.')
        for name in ('barcode','target_found','stamp','state','reason','evidence',
                     'other_barcodes','source_signature','first_page_error'):
            setattr(self,name,getattr(result,name))


@dataclass
class DocumentGroup:
    number: str
    pages: list[PageResult] = field(default_factory=list)


@dataclass
class DocumentContext:
    """Stamp decisions depend on preceding pages in the same source PDF."""
    source: str | None = None
    after_noncover: bool = False

    def apply(self,page,settings):
        if page.source != self.source:
            self.source=page.source
            self.after_noncover=False
        if not page.target_found or not page.number or page.stamp not in ('mixed','black','faint'):
            return False
        phase='later' if self.after_noncover else 'initial'
        kind='mixed' if page.stamp=='mixed' else 'plain'
        ask=getattr(settings,f'review_{phase}_{kind}')
        description='Renkli ve renksiz mühür birlikte bulundu.' if kind=='mixed' else 'Yalnızca renksiz mühür bulundu.'
        if ask:
            page.state,page.reason='review',description+' Kapak olamaz; sağdaki panelden inceleyin. Analiz devam eder.'
        else:
            page.state,page.reason='attachment',description+' Ayar gereği soru sorulmadan devam sayfası yapıldı.'
        return ask and not page.decision

    def record(self,page):
        if page.effective_state=='attachment':
            self.after_noncover=True


def build_groups(pages, grouping='shared'):
    """Never merge sources implicitly and never silently drop a page."""
    groups, unassigned = [], []
    source = None
    active = []
    adjacent = False
    blocked = False
    for page in pages:
        if page.source != source:
            source, active, adjacent, blocked = page.source, [], False, False
        state = page.effective_state
        if state in ('review', 'pending'):
            unassigned.append(page)
            # A possible document boundary makes following assignments unsafe.
            active, adjacent, blocked = [], False, True
        elif state == 'cover':
            if not page.number:
                unassigned.append(page)
                active, adjacent, blocked = [], False, True
                continue
            group = DocumentGroup(page.number, [page])
            groups.append(group)
            if grouping == 'shared' and adjacent and not blocked:
                active.append(group)
            else:
                active = [group]
            adjacent, blocked = True, False
        elif state == 'attachment':
            if active and not blocked:
                for group in active:
                    group.pages.append(page)
                adjacent = False
            else:
                unassigned.append(page)
    return groups, unassigned
