"""Optional desktop integration checks; enable with ARAR_UI_TESTS=1."""
import os
import gc
import tempfile
import threading
import time
import tkinter as tk
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from local_dependencies import activate_local_dependencies
activate_local_dependencies()
from pypdf import PdfWriter
from arar.app import ArarApp
from arar.models import PageResult, Settings, build_groups


@unittest.skipUnless(os.environ.get('ARAR_UI_TESTS')=='1','Masaüstü testi için ARAR_UI_TESTS=1 ayarlayın.')
class DesktopTests(unittest.TestCase):
    def setUp(self):
        # Collect closed Tk fixtures on the UI thread, before starting workers.
        gc.collect()
        self.temp=tempfile.TemporaryDirectory()
        self.source=Path(self.temp.name)/'pages.pdf'
        writer=PdfWriter()
        writer.add_blank_page(width=595,height=842)
        writer.add_blank_page(width=595,height=842)
        with self.source.open('wb') as handle:
            writer.write(handle)
        self.root=tk.Tk()
        with patch('arar.app.Settings.load',return_value=Settings(notify_analysis_done=False)):
            self.app=ArarApp(self.root)
        self.app.pages=[PageResult(str(self.source),i) for i in range(2)]
        self.app.sources=[str(self.source)]
        self.app._refresh()
        self.root.update()
        self.gate=threading.Event()

    def tearDown(self):
        self.app.cancel.set()
        self.app.resume.set()
        self.gate.set()
        self.pump_until(lambda:not self.app.busy)
        self.app.close()
        # A preview already rendering when the window closes can briefly hold
        # the fixture PDF open on Windows. Wait for that worker to release it.
        deadline=time.monotonic()+5
        while True:
            try:
                self.temp.cleanup()
                break
            except PermissionError:
                if time.monotonic()>=deadline:
                    raise
                time.sleep(.02)
        self.app=None
        self.root=None
        gc.collect()

    def descendants(self,parent):
        result=[]
        for child in parent.winfo_children():
            result.append(child)
            result.extend(self.descendants(child))
        return result

    def pump_until(self,condition,timeout=10):
        deadline=time.monotonic()+timeout
        while not condition() and time.monotonic()<deadline:
            self.root.update()
            time.sleep(.01)
        self.root.update()
        self.assertTrue(condition(),'Arayüz işlemi zamanında tamamlanmadı.')

    def test_stamp_thresholds_are_saved_and_invalid_values_are_rejected(self):
        with patch('arar.models.ROOT',Path(self.temp.name)):
            self.app.show_settings()
            self.root.update()
            dialog=next(widget for widget in self.root.winfo_children() if isinstance(widget,tk.Toplevel))
            inputs=[child for child in self.descendants(dialog) if child.winfo_class()=='TSpinbox']
            self.assertEqual([field.get() for field in inputs],['85','74'])
            save=next(widget for widget in self.descendants(dialog) if widget.winfo_class()=='TButton' and widget.cget('text')=='Ayarları kaydet')
            inputs[0].set('0')
            with patch('arar.app.messagebox.showerror') as error:
                save.invoke()
                error.assert_called_once()
            self.assertTrue(dialog.winfo_exists())
            self.assertEqual(self.app.settings.stamp_threshold,85)
            inputs[0].set('78')
            inputs[1].set('68')
            save.invoke()
            self.root.update()
            loaded=Settings.load()
            self.assertEqual((loaded.stamp_threshold,loaded.scan_stamp_threshold),(78,68))

    def test_defaults_restore_every_setting_only_after_save(self):
        previous=Settings(grouping='sequential',pause_on_later_barcode=True,confirm_cover=False,
            notify_analysis_done=False,stamp_threshold=95,scan_stamp_threshold=90,
            review_other_barcodes=False,review_missing_stamp=False,examples_dir=self.temp.name,
            output_dir=self.temp.name,review_initial_mixed=False,review_initial_plain=False,
            review_later_mixed=True,review_later_plain=True)
        self.app.settings=previous
        with patch('arar.models.ROOT',Path(self.temp.name)):
            previous.save()
            self.app.show_settings()
            self.root.update()
            dialog=next(widget for widget in self.root.winfo_children() if isinstance(widget,tk.Toplevel))
            reset=next(widget for widget in self.descendants(dialog) if widget.winfo_class()=='TButton'
                       and widget.cget('text')=='Varsayılana dön')
            reset.invoke()
            self.root.update()
            inputs=[widget for widget in self.descendants(dialog) if widget.winfo_class()=='TSpinbox']
            self.assertEqual([widget.get() for widget in inputs],['85','74'])
            self.assertIs(self.app.settings,previous)
            self.assertEqual(Settings.load().stamp_threshold,95)
            save=next(widget for widget in self.descendants(dialog) if widget.winfo_class()=='TButton'
                      and widget.cget('text')=='Ayarları kaydet')
            save.invoke()
            self.root.update()
            self.assertEqual(asdict(self.app.settings),asdict(Settings()))
            self.assertEqual(asdict(Settings.load()),asdict(Settings()))

    def test_stamp_explanations_and_footer_fit_in_settings_window(self):
        self.app.show_settings()
        self.root.update()
        dialog=next(widget for widget in self.root.winfo_children() if isinstance(widget,tk.Toplevel))
        tabs=next(widget for widget in dialog.winfo_children() if widget.winfo_class()=='TNotebook')
        tabs.select(1)
        self.root.update()
        accuracy=dialog.nametowidget(tabs.tabs()[1])
        text=' '.join(widget.cget('text') for widget in accuracy.winfo_children() if widget.winfo_class()=='Label')
        self.assertIn('%85 doğru sonuç garantisi değildir',text)
        self.assertIn('ayrı bir görsel',text)
        self.assertIn('sayfanın tamamı tek bir',text)
        self.assertIn('yanlış eşleşmeler artabilir',text)
        for widget in accuracy.winfo_children():
            self.assertLessEqual(widget.winfo_y()+widget.winfo_height(),accuracy.winfo_height())
        for widget in self.descendants(dialog):
            if widget.winfo_class()=='TButton' and widget.cget('text') in ('Varsayılana dön','Ayarları kaydet'):
                self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),dialog.winfo_rooty()+dialog.winfo_height())
        dialog.destroy()

    def test_page_headings_sort_without_changing_pdf_order_or_selection_identity(self):
        self.app.pages=[PageResult(str(self.source),0,state='cover',barcode='B10'),
                        PageResult(str(self.source),1,state='attachment',barcode='B2'),
                        PageResult(str(self.source),9,state='review',barcode='B1')]
        self.app._refresh()
        self.root.update()
        tree=self.app.page_tree
        self.root.tk.call(tree.heading('page','command'))
        self.assertEqual(tree.get_children(),('0','1','2'))
        self.root.tk.call(tree.heading('page','command'))
        self.assertEqual(tree.get_children(),('2','1','0'))
        self.assertIn('▼',tree.heading('page','text'))
        self.app.sort_pages('state')
        self.assertEqual(tree.get_children(),('1','2','0'))
        self.app.sort_pages('state')
        self.assertEqual(tree.get_children(),('0','2','1'))
        self.app.sort_pages('number')
        self.assertEqual(tree.get_children(),('2','1','0'))
        tree.selection_set('1')
        self.root.update()
        self.assertEqual(self.app.selected,1)
        self.app.pages[0].manual_barcode='B0'
        self.app._update_row(0,self.app.pages[0])
        self.assertEqual(tree.get_children(),('0','2','1'))
        self.assertEqual(tree.selection(),('1',))
        self.assertEqual([p.index for p in self.app.pages],[0,1,9])
        groups,_=build_groups(self.app.pages,self.app.settings.grouping)
        self.assertEqual([p.index for p in groups[0].pages],[0,1])
        with patch('arar.app.messagebox.askyesno',return_value=True):
            self.app.barcode_var.set('MANUAL')
            self.app.cover_btn.invoke()
        self.assertEqual(self.app.pages[1].manual_barcode,'MANUAL')
        self.assertEqual(self.app.pages[1].decision,'cover')
        self.assertFalse(self.app.pages[0].decision)

    def test_multiple_selected_sources_are_removed_without_deleting_files(self):
        original=self.source.read_bytes()
        second=Path(self.temp.name)/'second.pdf'
        third=Path(self.temp.name)/'third.pdf'
        second.write_bytes(original)
        third.write_bytes(original)
        self.app.sources=[str(self.source),str(second),str(third)]
        self.app.pages=[PageResult(source,0) for source in self.app.sources]
        self.app._refresh()
        self.root.update()
        self.assertEqual(self.app.source_list.cget('selectmode'),'extended')
        self.app.source_list.selection_set(0)
        self.app.source_list.selection_set(2)
        self.app.remove_btn.invoke()
        self.root.update()
        self.assertEqual(self.app.sources,[str(second)])
        self.assertEqual([p.source for p in self.app.pages],[str(second)])
        for path in (self.source,second,third):
            self.assertEqual(path.read_bytes(),original)
        self.app.source_list.selection_set(0)
        self.app.remove_btn.invoke()
        self.root.update()
        self.assertFalse(self.app.pages)
        self.assertFalse(self.app.page_tree.get_children())

    def test_new_settings_and_example_folder_are_saved(self):
        with patch('arar.models.ROOT',Path(self.temp.name)):
            self.app.show_settings()
            self.root.update()
            dialog=next(widget for widget in self.root.winfo_children() if isinstance(widget,tk.Toplevel))
            checkbox=next(widget for widget in self.descendants(dialog) if widget.winfo_class()=='TCheckbutton'
                          and 'başka barkod bulunursa' in widget.cget('text'))
            checkbox.invoke()
            missing=next(widget for widget in self.descendants(dialog) if widget.winfo_class()=='TCheckbutton'
                         and widget.cget('text')=='Mühür bulunamazsa kullanıcı incelemesine al')
            missing.invoke()
            choose=next(widget for widget in self.descendants(dialog) if widget.winfo_class()=='TButton'
                        and widget.cget('text')=='Klasör seç')
            with patch('arar.app.filedialog.askdirectory',return_value=self.temp.name):
                choose.invoke()
            save=next(widget for widget in self.descendants(dialog) if widget.winfo_class()=='TButton' and widget.cget('text')=='Ayarları kaydet')
            save.invoke()
            self.root.update()
            loaded=Settings.load()
            self.assertFalse(loaded.review_other_barcodes)
            self.assertFalse(loaded.review_missing_stamp)
            self.assertEqual(Path(loaded.examples_dir),Path(self.temp.name).resolve())

    def test_example_folder_messages_and_recursive_pdf_import(self):
        with patch('arar.app.messagebox.showinfo') as info,patch('arar.app.messagebox.showwarning') as warning:
            self.app.example_btn.invoke()
            info.assert_called_once()
            self.assertIn('Ayarlar',info.call_args.args[1])
            empty=Path(self.temp.name)/'empty'
            empty.mkdir()
            self.app.settings.examples_dir=str(empty)
            self.app.example_btn.invoke()
            warning.assert_called_once()
            self.assertIn('Klasörde PDF dosyası yok',warning.call_args.args[1])
        with patch('arar.app.messagebox.showerror') as error:
            self.app.settings.examples_dir=str(empty/'missing')
            self.app.example_btn.invoke()
            error.assert_called_once()
        nested=empty/'nested'
        nested.mkdir()
        destination=nested/'example.PDF'
        destination.write_bytes(self.source.read_bytes())
        self.app.settings.examples_dir=str(empty)
        with patch.object(self.app,'_import') as imported:
            self.app.example_btn.invoke()
            imported.assert_called_once_with([destination])

    def test_review_counter_excludes_attachments_waiting_for_cover(self):
        self.app.pages[0].state='review'
        self.app.pages[1].state='attachment'
        self.app._refresh()
        self.root.update()
        self.assertEqual(self.app.stats[2].cget('text'),'1')
        self.assertEqual(self.app.page_tree.item('1','tags'),('attachment',))
        self.assertEqual(str(self.app.export_btn.cget('state')),'disabled')
        self.app.pages[0].decision='cover'
        self.app.pages[0].manual_barcode='MANUAL'
        self.app._refresh_summary()
        self.assertEqual(self.app.stats[2].cget('text'),'0')
        self.assertEqual(str(self.app.export_btn.cget('state')),'normal')

    def test_reanalysis_resets_rows_scroll_progress_and_old_preview(self):
        self.app.pages=[PageResult(str(self.source),i,state='attachment') for i in range(35)]
        self.app._refresh()
        self.root.update()
        self.app.page_tree.selection_set('34')
        self.app.page_tree.yview_moveto(1)
        self.root.update()
        old_generation=self.app.preview_generation
        self.app.preview_cache[(str(self.source),1)]=('old',None)
        entered=threading.Event()
        def analyze(result,cancel,**kwargs):
            entered.set()
            self.gate.wait(10)
            result.state='cover' if result.index==0 else 'attachment'
            result.barcode='FIRST' if result.index==0 else ''
            return result
        with patch('arar.app.analyze_page',side_effect=analyze):
            self.app.analyze()
            self.pump_until(entered.is_set)
            self.assertEqual(self.app.page_tree.selection(),('0',))
            self.assertEqual(self.app.page_tree.yview()[0],0)
            self.assertEqual(self.app.pages[34].state,'pending')
            self.assertEqual(self.app.page_tree.item('34','values')[1],'Bekliyor')
            self.assertEqual(float(self.app.progress.cget('value')),0)
            self.assertNotIn((str(self.source),1),self.app.preview_cache)
            self.app.events.put(('preview',old_generation,(str(self.source),1),('old',None)))
            self.pump_until(lambda:self.app.events.empty())
            self.assertNotIn((str(self.source),1),self.app.preview_cache)
            self.gate.set()
            self.pump_until(lambda:not self.app.busy)

    def test_first_page_error_is_displayed(self):
        def analyze(result,cancel,**kwargs):
            result.state='review' if result.index==0 else 'attachment'
            result.first_page_error=result.index==0
            result.reason='İlk sayfada Receiving Report No ve herhangi bir mühür bulunamadı.'
            return result
        with patch('arar.app.analyze_page',side_effect=analyze),patch('arar.app.messagebox.showerror') as error:
            self.app.analyze()
            self.pump_until(lambda:not self.app.busy)
            error.assert_called_once()
            self.assertEqual(error.call_args.args[0],'İlk sayfa kontrolü')
            self.assertEqual(self.app.pages[1].state,'pending')

    def test_first_page_with_barcode_or_stamp_does_not_prompt_or_stop(self):
        for stamp,barcode in (('mixed','FIRST'),('black','FIRST'),('faint','FIRST'),
                              ('none','FIRST'),('blue',''),('black','')):
            with self.subTest(stamp=stamp,barcode=barcode):
                self.app.pages=[PageResult(str(self.source),i) for i in range(2)]
                processed=[]
                def analyze(result,cancel,**kwargs):
                    processed.append(result.index)
                    result.state='review' if result.index==0 else 'attachment'
                    result.barcode=barcode if result.index==0 else ''
                    result.target_found=result.index==0 and bool(barcode)
                    result.stamp=stamp if result.index==0 else 'none'
                    return result
                with patch('arar.app.analyze_page',side_effect=analyze), \
                        patch('arar.app.messagebox.askyesno') as question, \
                        patch('arar.app.messagebox.showerror') as error:
                    self.app.analyze()
                    self.pump_until(lambda:not self.app.busy)
                question.assert_not_called()
                error.assert_not_called()
                self.assertEqual(processed,[0,1])
                self.assertEqual(self.app.pages[0].effective_state,'review')
                self.assertFalse(self.app.pages[0].first_page_error)

    def test_nonblue_pages_follow_review_settings_without_prompting(self):
        for stamp,field in (('mixed','review_later_mixed'),('black','review_later_plain'),('faint','review_later_plain')):
            for ask in (False,True):
                with self.subTest(stamp=stamp,ask=ask):
                    self.app.pages=[PageResult(str(self.source),i) for i in range(3)]
                    setattr(self.app.settings,field,ask)
                    def analyze(result,cancel,**kwargs):
                        result.barcode='FIRST' if result.index==0 else 'LATER' if result.index==2 else ''
                        result.target_found=result.index in (0,2)
                        result.stamp='blue' if result.index==0 else stamp if result.index==2 else 'none'
                        result.state='cover' if result.index==0 else 'review' if result.index==2 else 'attachment'
                        return result
                    with patch('arar.app.analyze_page',side_effect=analyze), \
                            patch('arar.app.messagebox.askyesno',return_value=True) as question:
                        self.app.analyze()
                        self.pump_until(lambda:not self.app.busy)
                    question.assert_not_called()
                    self.assertEqual(self.app.pages[2].effective_state,'review' if ask else 'attachment')

    def test_old_later_barcode_pause_setting_does_not_prompt(self):
        self.app.settings.pause_on_later_barcode=True
        def analyze(result,cancel,**kwargs):
            result.barcode='FIRST' if result.index==0 else 'SECOND'
            result.target_found=True
            result.stamp='blue'
            result.state='cover'
            return result
        with patch('arar.app.analyze_page',side_effect=analyze), \
                patch('arar.app.messagebox.askyesno') as question, \
                patch('arar.app.messagebox.askokcancel') as continuation, \
                patch('arar.app.messagebox.showerror') as error:
            self.app.analyze()
            self.pump_until(lambda:not self.app.busy)
        question.assert_not_called()
        continuation.assert_not_called()
        error.assert_not_called()
        self.assertEqual([page.effective_state for page in self.app.pages],['cover','cover'])

    def test_stamp_question_settings_are_saved(self):
        with patch('arar.models.ROOT',Path(self.temp.name)):
            self.app.show_settings()
            self.root.update()
            dialog=next(widget for widget in self.root.winfo_children() if isinstance(widget,tk.Toplevel))
            fields=[widget for widget in self.descendants(dialog) if widget.winfo_class()=='TCheckbutton'
                    and widget.cget('text') in ('Mavi + renksiz mühür birlikteyse incelemeye al','Yalnızca renksiz mühür varsa incelemeye al')]
            self.assertEqual([widget.instate(['selected']) for widget in fields],[True,True,False,False])
            for widget in fields:
                widget.invoke()
            save=next(widget for widget in self.descendants(dialog) if widget.winfo_class()=='TButton'
                      and widget.cget('text')=='Ayarları kaydet')
            save.invoke()
            self.root.update()
            loaded=Settings.load()
            self.assertEqual([loaded.review_initial_mixed,loaded.review_initial_plain,
                              loaded.review_later_mixed,loaded.review_later_plain],[False,False,True,True])

    def test_analysis_uses_snapshot_of_selected_stamp_thresholds(self):
        values=[]
        self.app.settings.stamp_threshold=78
        self.app.settings.scan_stamp_threshold=68
        def analyze(result,cancel,**thresholds):
            values.append(thresholds)
            result.state='cover' if result.index==0 else 'attachment'
            result.barcode='FIRST' if result.index==0 else ''
            if result.index==0:
                self.gate.wait(10)
            return result
        with patch('arar.app.analyze_page',side_effect=analyze):
            self.app.analyze()
            self.pump_until(lambda:len(values)==1)
            self.app.settings.stamp_threshold=95
            self.gate.set()
            self.pump_until(lambda:not self.app.busy)
        self.assertEqual(values,[{'stamp_threshold':.78,'scan_stamp_threshold':.68,
                                 'review_other_barcodes':True,'review_missing_stamp':True}]*2)

    def test_review_while_next_page_is_analyzing(self):
        entered=threading.Event()
        def analyze(result,cancel,**thresholds):
            if result.index==1:
                entered.set()
                self.gate.wait(10)
            result.state='review' if result.index==0 else 'attachment'
            result.barcode='AUTO' if result.index==0 else ''
            result.reason='Test incelemesi'
            return result
        with patch('arar.app.analyze_page',side_effect=analyze),patch('arar.app.messagebox.askyesno',return_value=True):
            self.app.analyze()
            self.pump_until(lambda:entered.is_set() and self.app.pages[0].state=='review')
            self.assertTrue(self.app.busy)
            self.app.page_tree.selection_set('1')
            self.root.update()
            self.assertEqual(str(self.app.cover_btn.cget('state')),'disabled')
            self.app.page_tree.selection_set('0')
            self.root.update()
            self.assertEqual(str(self.app.cover_btn.cget('state')),'normal')
            self.app.barcode_var.set('MANUAL')
            self.app.cover_btn.invoke()
            self.assertEqual(self.app.pages[0].number,'MANUAL')
            self.assertEqual(self.app.page_tree.item('0','values')[0],'✓ 1')
            self.assertEqual(str(self.app.export_btn.cget('state')),'disabled')
            self.gate.set()
            self.pump_until(lambda:not self.app.busy)
            self.assertEqual(self.app.pages[0].decision,'cover')
            self.assertEqual(str(self.app.export_btn.cget('state')),'normal')

    def test_late_results_keep_manual_choices_and_unsaved_draft(self):
        self.app.pages[0].state='review'
        self.app.pages[0].barcode='BEFORE'
        self.app.pages[0].decision='cover'
        self.app.pages[0].manual_barcode='MANUAL'
        self.app._refresh()
        self.root.update()
        entered=threading.Event()
        def analyze(result,cancel,**thresholds):
            if result.index==0:
                entered.set()
                self.gate.wait(10)
            result.state='review' if result.index==0 else 'attachment'
            result.barcode='AFTER' if result.index==0 else ''
            return result
        with patch('arar.app.analyze_page',side_effect=analyze),patch('arar.app.messagebox.askyesno',return_value=True):
            self.app.analyze()
            self.pump_until(entered.is_set)
            self.app.barcode_var.set('UNSAVED-DRAFT')
            self.gate.set()
            self.pump_until(lambda:not self.app.busy)
            self.assertEqual(self.app.pages[0].barcode,'AFTER')
            self.assertEqual(self.app.pages[0].decision,'cover')
            self.assertEqual(self.app.pages[0].number,'MANUAL')
            self.assertEqual(self.app.barcode_var.get(),'UNSAVED-DRAFT')

    def test_clear_removes_workspace_but_preserves_source(self):
        original=self.source.read_bytes()
        self.app.pages[0].decision='cover'
        self.app.pages[0].manual_barcode='MANUAL'
        self.app.clear_btn.invoke()
        self.root.update()
        self.assertFalse(self.app.pages)
        self.assertFalse(self.app.sources)
        self.assertFalse(self.app.page_tree.get_children())
        self.assertFalse(self.app.group_tree.get_children())
        self.assertIsNone(self.app.preview_data)
        self.assertEqual(self.app.barcode_var.get(),'')
        self.assertEqual(self.source.read_bytes(),original)
        self.assertEqual([label.cget('text') for label in self.app.stats],['0','0','0','0'])
        self.assertEqual(str(self.app.export_btn.cget('state')),'disabled')

    def test_cover_confirmation_can_be_enabled_or_disabled(self):
        page=self.app.pages[0]
        page.state='review'
        page.barcode='AUTO'
        self.app._refresh()
        self.root.update()
        for enabled,answer,decision in ((True,False,''),(True,True,'cover'),(False,False,'cover')):
            with self.subTest(enabled=enabled,answer=answer):
                page.decision=''
                page.manual_barcode=''
                self.app.settings.confirm_cover=enabled
                self.app.barcode_var.set('MANUAL')
                with patch('arar.app.messagebox.askyesno',return_value=answer) as confirm:
                    self.app.cover_btn.invoke()
                self.assertEqual(confirm.call_count,int(enabled))
                self.assertEqual(page.decision,decision)
                self.assertEqual(page.manual_barcode,'MANUAL' if decision else '')
        page.decision=''
        self.app.barcode_var.set('')
        with patch('arar.app.messagebox.askyesno') as confirm,patch('arar.app.messagebox.showwarning') as warning:
            self.app.cover_btn.invoke()
        confirm.assert_not_called()
        warning.assert_called_once()
        self.assertFalse(page.decision)

    def test_settings_checkbox_saves_and_reopens_with_chosen_value(self):
        with patch('arar.models.ROOT',Path(self.temp.name)):
            for enabled in (False,True):
                self.app.show_settings()
                self.root.update()
                dialog=next(widget for widget in self.root.winfo_children() if isinstance(widget,tk.Toplevel))
                checkbox=next(widget for widget in self.descendants(dialog)
                              if widget.winfo_class()=='TCheckbutton' and widget.cget('text')=='Kapak olarak işaretlerken onay sor')
                self.assertEqual(checkbox.instate(['selected']),not enabled)
                checkbox.invoke()
                save=next(widget for widget in self.descendants(dialog) if widget.winfo_class()=='TButton' and widget.cget('text')=='Ayarları kaydet')
                self.assertLessEqual(save.winfo_rooty()+save.winfo_height(),dialog.winfo_rooty()+dialog.winfo_height())
                save.invoke()
                self.root.update()
                self.assertFalse(dialog.winfo_exists())
                self.app.settings=Settings.load()
                self.assertEqual(self.app.settings.confirm_cover,enabled)

    def test_completion_notice_is_optional_and_not_shown_after_stop(self):
        for enabled,cancelled in ((True,False),(False,False),(True,True)):
            with self.subTest(enabled=enabled,cancelled=cancelled):
                self.app.settings.notify_analysis_done=enabled
                self.app.pages[0].state='review'
                self.app.pages[1].state='attachment'
                self.app._set_busy(True)
                self.app.events.put(('analysis_done',cancelled))
                with patch('arar.app.messagebox.showinfo') as notice:
                    self.pump_until(lambda:not self.app.busy)
                if enabled and not cancelled:
                    notice.assert_called_once()
                    self.assertEqual(notice.call_args.args[0],'Tarama bitti')
                    self.assertIn('İnceleme bekleyen sayfa: 1',notice.call_args.args[1])
                else:
                    notice.assert_not_called()

    def test_completion_notice_setting_is_saved(self):
        with patch('arar.models.ROOT',Path(self.temp.name)):
            for enabled in (True,False):
                self.app.show_settings()
                self.root.update()
                dialog=next(widget for widget in self.root.winfo_children() if isinstance(widget,tk.Toplevel))
                checkbox=next(widget for widget in self.descendants(dialog)
                              if widget.winfo_class()=='TCheckbutton' and widget.cget('text')=='Tarama bittiğinde uyarı göster')
                self.assertEqual(checkbox.instate(['selected']),not enabled)
                checkbox.invoke()
                save=next(widget for widget in self.descendants(dialog) if widget.winfo_class()=='TButton' and widget.cget('text')=='Ayarları kaydet')
                self.assertLessEqual(save.winfo_rooty()+save.winfo_height(),dialog.winfo_rooty()+dialog.winfo_height())
                save.invoke()
                self.root.update()
                self.app.settings=Settings.load()
                self.assertEqual(self.app.settings.notify_analysis_done,enabled)

    def test_confirmation_updates_original_page_if_selection_changes(self):
        self.app.pages[0].decision='cover'
        self.app.pages[0].manual_barcode='AUTO'
        entered=threading.Event()
        def analyze(result,cancel,**thresholds):
            if result.index==1:
                entered.set()
                self.gate.wait(10)
            result.state='review' if result.index==0 else 'attachment'
            result.barcode='AUTO' if result.index==0 else ''
            return result
        def confirm(*args,**kwargs):
            self.gate.set()
            self.pump_until(lambda:not self.app.busy)
            self.app.page_tree.selection_set('1')
            self.root.update()
            return True
        with patch('arar.app.analyze_page',side_effect=analyze),patch('arar.app.messagebox.askyesno',side_effect=confirm):
            self.app.analyze()
            self.pump_until(lambda:entered.is_set() and self.app.pages[0].state=='review')
            self.app.barcode_var.set('MANUAL')
            self.app.cover_btn.invoke()
            self.assertEqual(self.app.pages[0].number,'MANUAL')
            self.assertEqual(self.app.page_tree.item('0','values')[0],'✓ 1')
            self.assertFalse(self.app.pages[1].decision)
