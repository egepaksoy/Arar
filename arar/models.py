from dataclasses import dataclass, field, asdict
from pathlib import Path
import json
from .offline import local_path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    grouping: str = 'sequential'
    pause_on_later_barcode: bool = False
    output_dir: str = str(ROOT / 'Çıktı')
    confirm_cover: bool = True
    notify_analysis_done: bool = True

    @classmethod
    def load(cls):
        try:
            data = json.loads((ROOT / '.arar' / 'settings.json').read_text(encoding='utf-8'))
            settings = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            if settings.grouping not in ('shared', 'sequential'):
                settings.grouping = 'sequential'
            settings.pause_on_later_barcode = bool(settings.pause_on_later_barcode)
            settings.confirm_cover = bool(settings.confirm_cover)
            settings.notify_analysis_done = bool(settings.notify_analysis_done)
            settings.output_dir = str(local_path(settings.output_dir))
            return settings
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self):
        local_path(self.output_dir)
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
                     'other_barcodes','source_signature'):
            setattr(self,name,getattr(result,name))


@dataclass
class DocumentGroup:
    number: str
    pages: list[PageResult] = field(default_factory=list)


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
