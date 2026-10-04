"""Turkish, native desktop interface. No browser, server, or network client."""
from pathlib import Path
from collections import OrderedDict
from dataclasses import replace
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from .models import Settings, ROOT, build_groups
from .detection import analyze_page, list_pages, render_page
from .exporter import export_groups
from .offline import local_path

BG='#f3f6fb'
WHITE='#ffffff'
NAVY='#12263f'
TEXT='#172b45'
MUTED='#64758a'
LINE='#e1e7ef'
TEAL='#087f8c'
AMBER='#aa6910'
GREEN='#16803d'
RED='#c62828'
STATE_LABELS={'pending':'Bekliyor','cover':'Kapak','attachment':'Devam','review':'İncele'}
STAMP_LABELS={'none':'Bulunamadı','blue':'Mavi mühür','black':'Siyah mühür',
              'faint':'Soluk / renksiz mühür','mixed':'Birden fazla mühür türü'}


class ArarApp:
    def __init__(self,root):
        self.root=root
        self.settings=Settings.load()
        self.pages=[]
        self.sources=[]
        self.events=queue.Queue()
        self.cancel=threading.Event()
        self.resume=threading.Event()
        self.busy=False
        self.operation=None
        self.review_during_analysis=False
        self.inspected_key=None
        self.inspected_number=''
        self.closing=False
        self.selected=None
        self.preview_generation=0
        self.preview_cache=OrderedDict()
        self.preview_data=None
        self.preview_zoom=1.0
        self.preview_layout=None
        self.zoom_var=tk.StringVar(value='100%')
        self.photo=None
        self.debounce=None
        self.barcode_var=tk.StringVar()
        self.status_var=tk.StringVar(value='PDF ekleyerek başlayın. Tüm işlemler bu bilgisayarda yapılır.')
        self.root.title('Arar • Belge ayırma')
        width=min(1440,max(1120,self.root.winfo_screenwidth()-80))
        height=min(930,max(760,self.root.winfo_screenheight()-120))
        x=max(0,(self.root.winfo_screenwidth()-width)//2)
        y=max(0,(self.root.winfo_screenheight()-height)//2-20)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        self.root.minsize(1120,760)
        self.root.configure(bg=BG)
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self._styles()
        self._layout()
        self._refresh()
        self.poll_after=self.root.after(80,self._poll)

    def _styles(self):
        style=ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.',font=('Segoe UI',10))
        style.configure('Treeview',background=WHITE,fieldbackground=WHITE,
                        foreground=TEXT,rowheight=32,borderwidth=0)
        style.configure('Treeview.Heading',background='#eef3f9',foreground=MUTED,
                        font=('Segoe UI',9,'bold'),padding=(6,9),relief='flat')
        style.map('Treeview',background=[('selected','#d9eef0')],foreground=[('disabled',MUTED)])
        style.configure('TButton',background=WHITE,foreground=TEXT,padding=(13,9),borderwidth=1)
        style.map('TButton',background=[('active','#e7eef6'),('disabled','#f0f2f5')],
                  foreground=[('disabled','#96a0ad')])
        style.configure('Primary.TButton',background=TEAL,foreground=WHITE,borderwidth=0,
                        font=('Segoe UI',10,'bold'))
        style.map('Primary.TButton',background=[('active','#066a75'),('disabled','#9bbec2')],
                  foreground=[('disabled',WHITE)])
        style.configure('Compact.TButton',font=('Segoe UI',9),padding=(6,8))
        style.configure('TCheckbutton',background=WHITE,foreground=TEXT)
        style.configure('TRadiobutton',background=WHITE,foreground=TEXT)
        style.configure('TEntry',padding=8,fieldbackground=WHITE)
        style.configure('Horizontal.TProgressbar',background=TEAL,troughcolor=LINE,borderwidth=0)

    def label(self,parent,text,*,size=10,bold=False,color=TEXT,bg=WHITE,**kwargs):
        return tk.Label(parent,text=text,font=('Segoe UI',size,'bold' if bold else 'normal'),
                        fg=color,bg=bg,**kwargs)

    def _layout(self):
        self.root.grid_columnconfigure(0,weight=1)
        self.root.grid_rowconfigure(2,weight=1)

        toolbar=tk.Frame(self.root,bg=BG)
        toolbar.grid(row=0,column=0,sticky='ew',padx=24,pady=(20,14))
        toolbar.grid_columnconfigure(0,weight=1)
        self.label(toolbar,'Belge çalışma alanı',size=21,bold=True,bg=BG).grid(row=0,column=0,sticky='w')
        self.label(toolbar,'PDF’leri ekleyin, kapakları kontrol edin ve belgeleri kaydedin.',color=MUTED,bg=BG).grid(row=1,column=0,sticky='w',pady=(4,0))
        controls=tk.Frame(toolbar,bg=BG)
        controls.grid(row=0,column=1,rowspan=2)
        self.add_btn=ttk.Button(controls,text='+ PDF ekle',command=self.add_files)
        self.add_btn.pack(side='left',padx=4)
        self.example_btn=ttk.Button(controls,text='Örnekleri aç',command=self.add_examples)
        self.example_btn.pack(side='left',padx=4)
        self.analyze_btn=ttk.Button(controls,text='Analizi başlat',style='Primary.TButton',command=self.analyze)
        self.analyze_btn.pack(side='left',padx=4)
        self.stop_btn=ttk.Button(controls,text='Durdur',command=self.stop,state='disabled')
        self.stop_btn.pack(side='left',padx=4)
        self.settings_btn=ttk.Button(controls,text='Ayarlar',command=self.show_settings)
        self.settings_btn.pack(side='left',padx=(12,0))

        stats=tk.Frame(self.root,bg=BG)
        stats.grid(row=1,column=0,sticky='ew',padx=24,pady=(0,16))
        self.stats=[]
        for i,(title,subtitle,color) in enumerate([
            ('TOPLAM SAYFA','İçe aktarılan PDF sayfaları',TEXT),
            ('KAPAK SAYFASI','Belge başlangıcı olarak seçilen',TEAL),
            ('İNCELEME BEKLİYOR','Karar veya gruplama gereken',AMBER),
            ('OLUŞACAK BELGE','Kayıt öncesi belge grupları',TEXT)]):
            stats.grid_columnconfigure(i,weight=1,uniform='stats')
            card=tk.Frame(stats,bg=WHITE,highlightbackground=LINE,highlightthickness=1)
            card.grid(row=0,column=i,sticky='ew',padx=(0 if i==0 else 8,0))
            self.label(card,title,size=9,bold=True,color=MUTED).pack(anchor='w',padx=16,pady=(12,0))
            number=self.label(card,'0',size=25,bold=True,color=color)
            number.pack(anchor='w',padx=16)
            self.label(card,subtitle,size=9,color=MUTED).pack(anchor='w',padx=16,pady=(0,12))
            self.stats.append(number)

        body=tk.Frame(self.root,bg=BG)
        body.grid(row=2,column=0,sticky='nsew',padx=24,pady=(0,16))
        body.grid_rowconfigure(0,weight=1)
        body.grid_columnconfigure(1,weight=1)
        left=tk.Frame(body,bg=WHITE,width=264,highlightbackground=LINE,highlightthickness=1)
        left.grid(row=0,column=0,sticky='nsew',padx=(0,12))
        left.grid_propagate(False)
        left.grid_columnconfigure(0,weight=1)
        left.grid_rowconfigure(4,weight=1)
        self.label(left,'KAYNAK DOSYALAR',size=9,bold=True,color=MUTED).grid(row=0,column=0,sticky='w',padx=14,pady=(14,8))
        self.source_list=tk.Listbox(left,height=4,font=('Segoe UI',9),bg=WHITE,fg=TEXT,
                                   selectbackground='#d9eef0',selectforeground=NAVY,
                                   borderwidth=0,highlightthickness=0,exportselection=False)
        self.source_list.grid(row=1,column=0,sticky='ew',padx=12)
        self.source_list.bind('<<ListboxSelect>>',self._source_selected)
        file_actions=tk.Frame(left,bg=WHITE)
        file_actions.grid(row=2,column=0,sticky='ew',padx=12,pady=(6,10))
        self.remove_btn=ttk.Button(file_actions,text='Dosyayı kaldır',style='Compact.TButton',command=self.remove_source)
        self.remove_btn.pack(side='left')
        self.clear_btn=ttk.Button(file_actions,text='Dosyaları temizle',style='Compact.TButton',command=self.clear_files)
        self.clear_btn.pack(side='left',padx=(6,0))
        self.label(left,'SAYFALAR',size=9,bold=True,color=MUTED).grid(row=3,column=0,sticky='w',padx=14,pady=(4,8))
        table_frame=tk.Frame(left,bg=WHITE)
        table_frame.grid(row=4,column=0,sticky='nsew',padx=8,pady=(0,8))
        table_frame.grid_rowconfigure(0,weight=1)
        table_frame.grid_columnconfigure(0,weight=1)
        self.page_tree=ttk.Treeview(table_frame,columns=('page','state','number'),show='headings',selectmode='browse')
        for key,title,width in [('page','Sayfa',55),('state','Durum',68),('number','Barkod',103)]:
            self.page_tree.heading(key,text=title)
            self.page_tree.column(key,width=width,minwidth=40,stretch=key=='number',anchor='w')
        self.page_tree.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(table_frame,orient='vertical',command=self.page_tree.yview)
        scroll.grid(row=0,column=1,sticky='ns')
        self.page_tree.configure(yscrollcommand=scroll.set)
        self.page_tree.tag_configure('cover',foreground=GREEN,background='#edf8f0')
        self.page_tree.tag_configure('attachment',foreground=GREEN,background='#edf8f0')
        self.page_tree.tag_configure('review',foreground=RED,background='#fff0f0')
        self.page_tree.tag_configure('pending',foreground=MUTED)
        self.page_tree.bind('<<TreeviewSelect>>',self._page_selected)

        center=tk.Frame(body,bg=WHITE,highlightbackground=LINE,highlightthickness=1)
        center.grid(row=0,column=1,sticky='nsew')
        center.grid_rowconfigure(2,weight=1)
        center.grid_columnconfigure(0,weight=1)
        self.preview_title=self.label(center,'Sayfa önizlemesi',bold=True,anchor='w')
        self.preview_title.grid(row=0,column=0,sticky='ew',padx=16,pady=12)
        zoom_bar=tk.Frame(center,bg=WHITE)
        zoom_bar.grid(row=1,column=0,sticky='ew',padx=12,pady=(0,8))
        self.zoom_out_btn=ttk.Button(zoom_bar,text='−',width=3,command=lambda:self.change_zoom(self.preview_zoom/1.25))
        self.zoom_out_btn.pack(side='left')
        tk.Label(zoom_bar,textvariable=self.zoom_var,width=6,font=('Segoe UI',10),fg=TEXT,bg=WHITE).pack(side='left',padx=2)
        self.zoom_in_btn=ttk.Button(zoom_bar,text='+',width=3,command=lambda:self.change_zoom(self.preview_zoom*1.25))
        self.zoom_in_btn.pack(side='left')
        self.zoom_fit_btn=ttk.Button(zoom_bar,text='Sayfaya sığdır',command=self.fit_preview)
        self.zoom_fit_btn.pack(side='left',padx=8)
        self.label(zoom_bar,'Ctrl + tekerlek',size=9,color=MUTED).pack(side='right')
        viewport=tk.Frame(center,bg='#dce4ee')
        viewport.grid(row=2,column=0,sticky='nsew')
        viewport.grid_rowconfigure(0,weight=1)
        viewport.grid_columnconfigure(0,weight=1)
        self.canvas=tk.Canvas(viewport,bg='#dce4ee',highlightthickness=0)
        self.canvas.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(viewport,orient='vertical',command=self.canvas.yview)
        vertical.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(viewport,orient='horizontal',command=self.canvas.xview)
        horizontal.grid(row=1,column=0,sticky='ew')
        self.canvas.configure(xscrollcommand=horizontal.set,yscrollcommand=vertical.set)
        self.canvas.bind('<Configure>',self._resize_preview)
        self.canvas.bind('<MouseWheel>',self._preview_wheel)
        self.canvas.bind('<ButtonPress-1>',lambda event:self.canvas.scan_mark(event.x,event.y))
        self.canvas.bind('<B1-Motion>',lambda event:self.canvas.scan_dragto(event.x,event.y,gain=1))
        legend=tk.Frame(center,bg=WHITE)
        legend.grid(row=3,column=0,sticky='ew',padx=16,pady=10)
        self.label(legend,'■ Barkod',size=9,color=TEAL).pack(side='left',padx=(0,12))
        self.label(legend,'■ Mavi mühür',size=9,color='#276ac4').pack(side='left',padx=(0,12))
        self.label(legend,'■ İncelenecek mühür',size=9,color=AMBER).pack(side='left')

        right_outer=tk.Frame(body,bg=WHITE,width=310,highlightbackground=LINE,highlightthickness=1)
        right_outer.grid(row=0,column=2,sticky='nsew',padx=(12,0))
        right_outer.grid_propagate(False)
        right_outer.grid_rowconfigure(0,weight=1)
        right_outer.grid_columnconfigure(0,weight=1)
        self.inspector_panel=right_outer
        self.inspector_canvas=tk.Canvas(right_outer,bg=WHITE,highlightthickness=0)
        self.inspector_canvas.grid(row=0,column=0,sticky='nsew')
        inspector_scroll=ttk.Scrollbar(right_outer,orient='vertical',command=self.inspector_canvas.yview)
        inspector_scroll.grid(row=0,column=1,sticky='ns')
        self.inspector_canvas.configure(yscrollcommand=inspector_scroll.set)
        right=tk.Frame(self.inspector_canvas,bg=WHITE)
        inspector_window=self.inspector_canvas.create_window(0,0,window=right,anchor='nw')
        right.bind('<Configure>',lambda e:self.inspector_canvas.configure(scrollregion=self.inspector_canvas.bbox('all')))
        self.inspector_canvas.bind('<Configure>',lambda e:self.inspector_canvas.itemconfigure(inspector_window,width=e.width))
        self.root.bind_all('<MouseWheel>',self._scroll_inspector,add='+')
        right.grid_columnconfigure(0,weight=1)
        self.label(right,'SAYFA KARARI',size=9,bold=True,color=MUTED).grid(row=0,column=0,sticky='w',padx=16,pady=(16,10))
        self.state_label=self.label(right,'Sayfa seçin',size=16,bold=True,anchor='w')
        self.state_label.grid(row=1,column=0,sticky='ew',padx=16)
        self.reason_label=self.label(right,'Analiz sonucu ve kullanıcı kararları burada görünür.',
                                     color=MUTED,anchor='nw',justify='left',wraplength=254)
        self.reason_label.grid(row=2,column=0,sticky='ew',padx=16,pady=(8,14))
        info=tk.Frame(right,bg=WHITE)
        info.grid(row=3,column=0,sticky='ew',padx=16)
        self.label(info,'MÜHÜR',size=9,bold=True,color=MUTED).pack(anchor='w')
        self.stamp_label=self.label(info,'—',bold=True)
        self.stamp_label.pack(anchor='w',pady=(3,12))
        self.label(info,'RECEIVING REPORT NO',size=9,bold=True,color=MUTED).pack(anchor='w')
        self.barcode_entry=ttk.Entry(info,textvariable=self.barcode_var)
        self.barcode_entry.bind('<KeyRelease>',self._review_interaction)
        self.barcode_entry.pack(fill='x',pady=(6,3))
        self.label(info,'Gerekirse barkodu elle düzeltin.',size=9,color=MUTED).pack(anchor='w')
        actions=tk.Frame(right,bg=WHITE)
        actions.grid(row=4,column=0,sticky='ew',padx=16,pady=14)
        self.cover_btn=ttk.Button(actions,text='Kapak olarak onayla',style='Primary.TButton',command=self.approve_cover)
        self.cover_btn.pack(fill='x',pady=(0,6))
        self.attach_btn=ttk.Button(actions,text='Devam sayfası olarak işaretle',command=self.approve_attachment)
        self.attach_btn.pack(fill='x',pady=(0,6))
        self.reset_btn=ttk.Button(actions,text='Otomatik karara dön',command=self.reset_decision)
        self.reset_btn.pack(fill='x')
        tk.Frame(right,bg=LINE,height=1).grid(row=5,column=0,sticky='ew',padx=16,pady=(0,10))
        self.label(right,'OLUŞACAK BELGELER',size=9,bold=True,color=MUTED).grid(row=6,column=0,sticky='w',padx=16)
        self.group_tree=ttk.Treeview(right,columns=('number','count'),show='headings',height=4,selectmode='none')
        self.group_tree.heading('number',text='PDF adı')
        self.group_tree.heading('count',text='Sayfa')
        self.group_tree.column('number',width=175,minwidth=80)
        self.group_tree.column('count',width=45,minwidth=35,stretch=False,anchor='center')
        self.group_tree.grid(row=7,column=0,sticky='ew',padx=12,pady=(8,0))
        self.group_tree.bind('<Double-1>',self.show_group_pages)
        self.group_hint=self.label(right,'Belge satırına çift tıklayarak sayfaları görün.',
                                  size=9,color=MUTED,wraplength=254,anchor='w',justify='left')
        self.group_hint.grid(row=8,column=0,sticky='ew',padx=16,pady=8)
        export=tk.Frame(right_outer,bg=WHITE)
        export.grid(row=1,column=0,columnspan=2,sticky='ew',padx=16,pady=(10,16))
        self.output_label=self.label(export,'',size=9,color=MUTED,wraplength=254,anchor='w',justify='left')
        self.output_label.pack(fill='x',pady=(0,8))
        self.export_btn=ttk.Button(export,text='Belgeleri kaydet',style='Primary.TButton',command=self.export)
        self.export_btn.pack(fill='x')

        footer=tk.Frame(self.root,bg=WHITE,highlightbackground=LINE,highlightthickness=1)
        footer.grid(row=3,column=0,sticky='ew')
        footer.grid_columnconfigure(0,weight=1)
        tk.Label(footer,textvariable=self.status_var,font=('Segoe UI',9),fg=MUTED,bg=WHITE,
                 anchor='w',wraplength=950,justify='left').grid(row=0,column=0,sticky='ew',padx=24,pady=12)
        self.progress=ttk.Progressbar(footer,mode='determinate',length=190)
        self.progress.grid(row=0,column=1,padx=24,pady=12)

    def _scroll_inspector(self,event):
        widget=self.root.winfo_containing(event.x_root,event.y_root)
        if widget is not None and str(widget).startswith(str(self.inspector_panel)):
            self.inspector_canvas.yview_scroll(-int(event.delta/120),'units')

    def _set_busy(self,value):
        self.busy=value
        if not value:
            self.operation=None
        state='disabled' if value else 'normal'
        for button in (self.add_btn,self.example_btn,self.remove_btn,self.clear_btn,self.settings_btn):
            button.configure(state=state)
        self.analyze_btn.configure(state='normal' if self.pages and not value else 'disabled')
        self.stop_btn.configure(state='normal' if value else 'disabled')
        self._refresh_summary()
        self._inspector()

    def add_files(self):
        if self.busy:
            return
        paths=filedialog.askopenfilenames(title='Yerel PDF dosyalarını seçin',filetypes=[('PDF belgeleri','*.pdf')])
        if paths:
            self._import(paths)

    def add_examples(self):
        if self.busy:
            return
        paths=sorted((ROOT/'Örnek').rglob('*.pdf'))
        if paths:
            self._import(paths)
        else:
            messagebox.showinfo('Örnekler','Örnek klasöründe PDF bulunamadı.')

    def _import(self,paths):
        self.cancel.clear()
        self.operation='import'
        self._set_busy(True)
        self.status_var.set('PDF sayfaları içe aktarılıyor…')
        def work():
            imported=[]
            errors=[]
            for value in paths:
                if self.cancel.is_set():
                    break
                try:
                    path=str(local_path(value,must_exist=True))
                    if path in self.sources:
                        continue
                    imported.extend(list_pages(path))
                except Exception as exc:
                    errors.append(Path(value).name+': '+str(exc))
            self.events.put(('imported',imported,errors))
        threading.Thread(target=work,daemon=True).start()

    def remove_source(self):
        indices=self.source_list.curselection()
        if self.busy or not indices:
            return
        source=self.sources[indices[0]]
        self.pages=[p for p in self.pages if p.source!=source]
        self.sources.remove(source)
        self.selected=None
        self.preview_cache.clear()
        self.preview_data=None
        self.preview_zoom=1.0
        self.preview_layout=None
        self.preview_generation+=1
        self._refresh()
        self._draw_preview()
        self.status_var.set(Path(source).name+' çalışma alanından kaldırıldı.')

    def clear_files(self):
        if self.busy:
            return
        self.pages.clear()
        self.sources.clear()
        self.selected=None
        self.preview_generation+=1
        self.preview_cache.clear()
        self.preview_data=None
        self.preview_layout=None
        self.preview_zoom=1.0
        self.photo=None
        self.preview_title.configure(text='Sayfa önizlemesi')
        self.progress.configure(value=0)
        self._refresh()
        self._draw_preview()
        self.status_var.set('Dosyalar çalışma alanından temizlendi. Yeni PDF ekleyebilirsiniz.')

    def _review_interaction(self,event=None):
        if self.operation=='analysis':
            self.review_during_analysis=True

    def _source_selected(self,event=None):
        selection=self.source_list.curselection()
        if selection:
            source=self.sources[selection[0]]
            index=next((i for i,p in enumerate(self.pages) if p.source==source),None)
            if index is not None:
                self.page_tree.selection_set(str(index))
                self.page_tree.see(str(index))

    def _page_selected(self,event=None):
        items=self.page_tree.selection()
        if not items:
            return
        index=int(items[0])
        if index>=len(self.pages):
            return
        self._review_interaction()
        if self.selected!=index:
            self.preview_zoom=1.0
            self.preview_layout=None
        self.selected=index
        page=self.pages[index]
        self._inspector()
        self.preview_title.configure(text=Path(page.source).name+'  •  Sayfa '+str(page.index+1))
        self.preview_generation+=1
        generation=self.preview_generation
        key=(page.source,page.index)
        if key in self.preview_cache:
            self.preview_data=self.preview_cache[key]
            self.preview_cache.move_to_end(key)
            self._draw_preview()
            return
        self.preview_data=None
        self._draw_preview('Önizleme hazırlanıyor…')
        def work():
            try:
                data=render_page(*key,max_size=(2400,3200))
                self.events.put(('preview',generation,key,data))
            except Exception as exc:
                self.events.put(('preview_error',generation,str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def _resize_preview(self,event=None):
        if self.debounce:
            self.root.after_cancel(self.debounce)
        self.debounce=self.root.after(80,self._draw_preview)

    def change_zoom(self,value,anchor=None):
        if not self.preview_data:
            return
        self.preview_zoom=max(.25,min(4.0,value))
        self._draw_preview(anchor=anchor)

    def fit_preview(self):
        self.preview_layout=None
        self.change_zoom(1.0)

    def _preview_wheel(self,event):
        if event.state & 0x4:
            self.change_zoom(self.preview_zoom*(1.25 if event.delta>0 else .8),(event.x,event.y))
        elif event.state & 0x1:
            self.canvas.xview_scroll(-int(event.delta/120),'units')
        else:
            self.canvas.yview_scroll(-int(event.delta/120),'units')
        return 'break'

    def _draw_preview(self,message='PDF ekleyin ve bir sayfa seçin.',anchor=None):
        if self.debounce:
            self.root.after_cancel(self.debounce)
        self.debounce=None
        width,height=self.canvas.winfo_width(),self.canvas.winfo_height()
        self.zoom_var.set(f'{round(self.preview_zoom*100)}%')
        enabled=bool(self.preview_data)
        self.zoom_fit_btn.configure(state='normal' if enabled else 'disabled')
        self.zoom_out_btn.configure(state='normal' if enabled and self.preview_zoom>.25 else 'disabled')
        self.zoom_in_btn.configure(state='normal' if enabled and self.preview_zoom<4 else 'disabled')
        if width<10 or height<10:
            return
        anchor=anchor or (width/2,height/2)
        point=(.5,.5)
        if self.preview_layout:
            old_x,old_y,old_w,old_h=self.preview_layout
            point=((self.canvas.canvasx(anchor[0])-old_x)/old_w,
                   (self.canvas.canvasy(anchor[1])-old_y)/old_h)
        self.canvas.delete('all')
        if not self.preview_data:
            self.preview_layout=None
            self.canvas.configure(scrollregion=(0,0,width,height),cursor='')
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
            self.canvas.create_text(width/2,height/2,text=message,fill=MUTED,
                                    font=('Segoe UI',12),width=max(80,width-50))
            return
        image,page_size=self.preview_data
        factor=min((width-36)/image.width,(height-28)/image.height)*self.preview_zoom
        w,h=max(1,int(image.width*factor)),max(1,int(image.height*factor))
        displayed=image.resize((w,h),Image.Resampling.LANCZOS)
        self.photo=ImageTk.PhotoImage(displayed)
        area_w,area_h=max(width,w+36),max(height,h+28)
        x,y=(area_w-w)/2,(area_h-h)/2
        self.preview_layout=(x,y,w,h)
        self.canvas.configure(scrollregion=(0,0,area_w,area_h),cursor='fleur' if area_w>width or area_h>height else '')
        self.canvas.create_rectangle(x+3,y+3,x+w+3,y+h+3,fill='#bdc8d7',outline='')
        self.canvas.create_image(x,y,image=self.photo,anchor='nw')
        if self.selected is not None and self.selected<len(self.pages):
            colors={'barcode':TEAL,'blue':'#276ac4','black':AMBER,'faint':AMBER}
            for item in self.pages[self.selected].evidence:
                a,b,c,d=item.box
                self.canvas.create_rectangle(x+a*w/page_size[0],y+b*h/page_size[1],
                                             x+c*w/page_size[0],y+d*h/page_size[1],
                                             outline=colors.get(item.kind,AMBER),width=2)
        self.canvas.xview_moveto(max(0,min((area_w-width)/area_w,(x+point[0]*w-anchor[0])/area_w)))
        self.canvas.yview_moveto(max(0,min((area_h-height)/area_h,(y+point[1]*h-anchor[1])/area_h)))

    def _can_review_selected(self):
        return (self.selected is not None and self.selected<len(self.pages) and
                self.pages[self.selected].state!='pending' and
                (not self.busy or self.operation=='analysis'))

    def _inspector(self,reset_barcode=False):
        page=self.pages[self.selected] if self.selected is not None and self.selected<len(self.pages) else None
        can_review=self._can_review_selected()
        for button in (self.cover_btn,self.attach_btn,self.reset_btn):
            button.configure(state='normal' if can_review else 'disabled')
        self.barcode_entry.configure(state='normal' if can_review else 'disabled')
        if not page:
            self.state_label.configure(text='Sayfa seçin',fg=TEXT)
            self.reason_label.configure(text='Analiz sonucu ve kullanıcı kararları burada görünür.')
            self.stamp_label.configure(text='—')
            self.barcode_var.set('')
            self.inspected_key=None
            self.inspected_number=''
            return
        state=page.effective_state
        label=STATE_LABELS[state]+(' • Onaylandı' if page.decision else '')
        self.state_label.configure(text=label,fg=TEAL if state=='cover' else AMBER if state=='review' else TEXT)
        self.reason_label.configure(text=('Kullanıcı kararı uygulandı.\n' if page.decision else '')+page.reason)
        self.stamp_label.configure(text=STAMP_LABELS[page.stamp])
        key=(page.source,page.index)
        has_draft=self.inspected_key==key and self.barcode_var.get()!=self.inspected_number
        if reset_barcode or not has_draft:
            self.barcode_var.set(page.number)
        self.inspected_key=key
        self.inspected_number=page.number

    def _refresh(self):
        self.source_list.delete(0,'end')
        for source in self.sources:
            count=sum(p.source==source for p in self.pages)
            self.source_list.insert('end',f'{Path(source).name}  ({count} sayfa)')
        self.page_tree.delete(*self.page_tree.get_children())
        for i,page in enumerate(self.pages):
            self._update_row(i,page)
        self._set_busy(self.busy)
        self._refresh_summary()
        if self.pages and self.selected is None:
            self.page_tree.selection_set('0')

    def _update_row(self,i,page):
        state=page.effective_state
        mark='✓ ' if state in ('cover','attachment') else '! ' if state=='review' else ''
        values=(mark+str(page.index+1),STATE_LABELS[state]+(' *' if page.decision else ''),page.number or '—')
        if self.page_tree.exists(str(i)):
            self.page_tree.item(str(i),values=values,tags=(page.effective_state,))
        else:
            self.page_tree.insert('','end',iid=str(i),values=values,tags=(page.effective_state,))

    def _refresh_summary(self):
        groups,unassigned=build_groups(self.pages,self.settings.grouping)
        counts=(len(self.pages),sum(p.effective_state=='cover' for p in self.pages),len(unassigned),len(groups))
        for label,number in zip(self.stats,counts):
            label.configure(text=str(number))
        self.group_tree.delete(*self.group_tree.get_children())
        for i,group in enumerate(groups):
            self.group_tree.insert('','end',iid=str(i),values=(group.number+'.pdf',len(group.pages)))
        self.group_hint.configure(text=f'{len(unassigned)} sayfa karar / gruplama bekliyor.' if unassigned else
                                  'Belge satırına çift tıklayarak sayfaları görün.')
        self.output_label.configure(text='Kayıt klasörü: '+self.settings.output_dir)
        self.export_btn.configure(state='normal' if groups and not unassigned and not self.busy else 'disabled')

    def analyze(self):
        if self.busy or not self.pages:
            return
        self.cancel.clear()
        self.operation='analysis'
        self.review_during_analysis=False
        self.resume.clear()
        self.progress.configure(maximum=len(self.pages),value=0)
        self._set_busy(True)
        self.status_var.set('Barkod ve mühürler bu bilgisayarda inceleniyor…')
        # Workers only mutate their own snapshots. User decisions live on the
        # UI thread and are preserved when queued automatic results arrive.
        snapshot=[replace(page,decision='',manual_barcode='') for page in self.pages]
        pause_setting=self.settings.pause_on_later_barcode
        def work():
            for i,page in enumerate(snapshot):
                if self.cancel.is_set():
                    break
                try:
                    analyze_page(page,self.cancel)
                except Exception as exc:
                    page.state,page.reason='review','Sayfa işlenemedi: '+str(exc)
                if self.cancel.is_set():
                    break
                self.events.put(('page',i,page))
                if pause_setting and page.target_found and page.index>0:
                    self.resume.clear()
                    self.events.put(('pause',i,page))
                    while not self.resume.wait(.1):
                        if self.cancel.is_set():
                            break
            self.events.put(('analysis_done',self.cancel.is_set()))
        threading.Thread(target=work,daemon=True).start()

    def stop(self):
        if self.busy:
            self.cancel.set()
            self.resume.set()
            self.status_var.set('İşlem durduruluyor…')
            self.stop_btn.configure(state='disabled')

    def approve_cover(self):
        if not self._can_review_selected():
            return
        index=self.selected
        page=self.pages[index]
        self._review_interaction()
        number=self.barcode_var.get().strip()
        if not number:
            messagebox.showwarning('Kapak numarası gerekli','Receiving Report numarasını girin.')
            return
        if page.state!='cover' and not messagebox.askyesno('Kapak kararını onaylayın',
                page.reason+'\n\nBu sayfayı kullanıcı kararıyla kapak yapmak istiyor musunuz?'):
            return
        page.manual_barcode=number
        page.decision='cover'
        self._decision_changed(index)

    def approve_attachment(self):
        if not self._can_review_selected():
            return
        page=self.pages[self.selected]
        page.decision='attachment'
        self._decision_changed()

    def reset_decision(self):
        if not self._can_review_selected():
            return
        page=self.pages[self.selected]
        page.decision=''
        page.manual_barcode=''
        self._decision_changed()

    def _decision_changed(self,index=None):
        self._review_interaction()
        index=self.selected if index is None else index
        self._update_row(index,self.pages[index])
        self._refresh_summary()
        self._inspector(reset_barcode=index==self.selected)
        self.status_var.set('Sayfa kararı güncellendi; analiz devam ediyor.' if self.operation=='analysis' else
                            'Sayfa kararı güncellendi. Belge grupları yeniden hesaplandı.')
        review=next((i for i,p in enumerate(self.pages) if p.effective_state=='review'),None)
        if review is not None:
            self.page_tree.selection_set(str(review))
            self.page_tree.see(str(review))

    def show_group_pages(self,event=None):
        item=self.group_tree.identify_row(event.y) if event else ''
        groups,_=build_groups(self.pages,self.settings.grouping)
        if item and int(item)<len(groups):
            group=groups[int(item)]
            lines=[f'{Path(p.source).name} • Sayfa {p.index+1}' for p in group.pages]
            messagebox.showinfo(group.number+'.pdf','\n'.join(lines))

    def export(self):
        if self.busy:
            return
        groups,unassigned=build_groups(self.pages,self.settings.grouping)
        if not groups or unassigned:
            messagebox.showwarning('İnceleme tamamlanmadı','Tüm sayfalar bir belgeye atanmalı ve kapak kararları tamamlanmalı.')
            return
        folder=filedialog.askdirectory(title='Yerel kayıt klasörünü seçin',initialdir=str(ROOT))
        if not folder:
            return
        try:
            folder=str(local_path(folder,must_exist=True))
        except (ValueError,OSError) as exc:
            messagebox.showerror('Yerel klasör gerekli',str(exc))
            return
        self.settings.output_dir=folder
        try:
            self.settings.save()
        except OSError:
            pass
        self._set_busy(True)
        self.stop_btn.configure(state='disabled')
        self.operation='export'
        self.status_var.set('Belgeler yerel klasöre kaydediliyor…')
        def work():
            try:
                self.events.put(('exported',export_groups(groups,folder)))
            except Exception as exc:
                self.events.put(('error','Kayıt başarısız: '+str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def show_settings(self):
        if self.busy:
            return
        dialog=tk.Toplevel(self.root)
        dialog.title('Arar • Ayarlar')
        dialog.geometry('590x425')
        dialog.resizable(False,False)
        dialog.configure(bg=WHITE)
        dialog.transient(self.root)
        dialog.grab_set()
        self.label(dialog,'Belge gruplama',size=17,bold=True).pack(anchor='w',padx=24,pady=(22,12))
        grouping=tk.StringVar(value=self.settings.grouping)
        ttk.Radiobutton(dialog,text='Her yeni kapakta ayrı belge başlat',variable=grouping,value='sequential').pack(anchor='w',padx=24,pady=7)
        self.label(dialog,'Program algoritması: sayfalar bir sonraki kapağa kadar eklenir.',
                   size=9,color=MUTED).pack(anchor='w',padx=47)
        ttk.Radiobutton(dialog,text='Art arda kapaklara ortak devam sayfalarını ekle',variable=grouping,value='shared').pack(anchor='w',padx=24,pady=(16,7))
        self.label(dialog,'Kurallar.pdf: peş peşe kapaklardan sonraki sayfalar her kapağa eklenir.',
                   size=9,color=MUTED).pack(anchor='w',padx=47)
        self.label(dialog,'Sonraki barkodlarda duraklama',size=12,bold=True).pack(anchor='w',padx=24,pady=(24,10))
        pause=tk.BooleanVar(value=self.settings.pause_on_later_barcode)
        ttk.Checkbutton(dialog,text='İlk sayfadan sonra Receiving Report barkodu bulunursa sor',variable=pause).pack(anchor='w',padx=24)
        self.label(dialog,'Belirsiz mühürler her iki ayarda da kullanıcı kararı bekler.',
                   size=9,color=MUTED).pack(anchor='w',padx=24,pady=12)
        def save():
            try:
                self.settings.grouping=grouping.get()
                self.settings.pause_on_later_barcode=pause.get()
                self.settings.save()
            except (OSError,ValueError) as exc:
                messagebox.showerror('Ayarlar kaydedilemedi',str(exc),parent=dialog)
                return
            dialog.destroy()
            self._refresh_summary()
            self.status_var.set('Ayarlar kaydedildi.')
        ttk.Button(dialog,text='Ayarları kaydet',style='Primary.TButton',command=save).pack(anchor='e',padx=24,pady=12)

    def _poll(self):
        self.poll_after=None
        if self.closing:
            return
        try:
            for _ in range(40):
                event=self.events.get_nowait()
                kind=event[0]
                if kind=='imported':
                    self.pages.extend(event[1])
                    self.sources=list(dict.fromkeys(p.source for p in self.pages))
                    self._set_busy(False)
                    self._refresh()
                    self.status_var.set(f'{len(event[1])} sayfa eklendi. Analizi başlatabilirsiniz.')
                    if event[2]:
                        messagebox.showwarning('Bazı dosyalar açılamadı','\n'.join(event[2]))
                elif kind=='page':
                    _,i,result=event
                    page=self.pages[i]
                    page.apply_analysis(result)
                    self._update_row(i,page)
                    self.progress.configure(value=i+1)
                    self.status_var.set(f'{i+1} / {len(self.pages)} sayfa incelendi • {Path(page.source).name}')
                    self._refresh_summary()
                    if self.selected==i:
                        self._inspector()
                        self._draw_preview()
                elif kind=='pause':
                    _,i,page=event
                    if not self.cancel.is_set():
                        self.page_tree.selection_set(str(i))
                        self.page_tree.see(str(i))
                        if not messagebox.askokcancel('Yeni barkod bulundu',
                                f'{Path(page.source).name} • Sayfa {page.index+1}\n'
                                f'Receiving Report No: {page.barcode}\n\nAnalize devam edilsin mi?'):
                            self.cancel.set()
                    self.resume.set()
                elif kind=='analysis_done':
                    self._set_busy(False)
                    self._refresh_summary()
                    self.status_var.set('Analiz durduruldu. İncelenmeyen sayfalar bekliyor.' if event[1] else
                                        'Analiz tamamlandı. İnceleme bekleyen sayfaları kontrol edin.')
                    review=next((i for i,p in enumerate(self.pages) if p.effective_state=='review'),None)
                    if review is not None and not self.review_during_analysis:
                        self.page_tree.selection_set(str(review))
                        self.page_tree.see(str(review))
                elif kind=='preview':
                    _,generation,key,data=event
                    if key[0] not in self.sources:
                        continue
                    self.preview_cache[key]=data
                    while len(self.preview_cache)>4:
                        self.preview_cache.popitem(last=False)
                    if generation==self.preview_generation:
                        self.preview_data=data
                        self._draw_preview()
                elif kind=='preview_error':
                    if event[1]==self.preview_generation:
                        self._draw_preview('Önizleme açılamadı: '+event[2])
                elif kind=='exported':
                    self._set_busy(False)
                    count=len(event[1])-1
                    self.status_var.set(f'{count} PDF ve işlem raporu kaydedildi: {self.settings.output_dir}')
                    messagebox.showinfo('Belgeler kaydedildi',f'{count} PDF kaydedildi.\n\n{self.settings.output_dir}\n\nİşlem raporu aynı klasörde bulunur.')
                elif kind=='error':
                    self._set_busy(False)
                    self.status_var.set(event[1])
                    messagebox.showerror('İşlem tamamlanamadı',event[1])
        except queue.Empty:
            pass
        self.poll_after=self.root.after(80,self._poll)

    def close(self):
        if self.operation=='export':
            messagebox.showinfo('Belgeler kaydediliyor','Kayıt tamamlandığında uygulamayı kapatabilirsiniz.')
            return
        if self.busy and not messagebox.askyesno('İşlem sürüyor','İşlemi sonlandırıp uygulamayı kapatmak istiyor musunuz?'):
            return
        self.closing=True
        self.cancel.set()
        self.resume.set()
        for timer in (self.poll_after,self.debounce):
            if timer:
                self.root.after_cancel(timer)
        self.root.destroy()


def main():
    root=tk.Tk()
    ArarApp(root)
    root.mainloop()
