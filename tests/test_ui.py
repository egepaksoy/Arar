"""Optional desktop integration checks; enable with ARAR_UI_TESTS=1."""
import os
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch
from local_dependencies import activate_local_dependencies
activate_local_dependencies()
from pypdf import PdfWriter
from arar.app import ArarApp
from arar.models import PageResult, Settings


@unittest.skipUnless(os.environ.get('ARAR_UI_TESTS')=='1','Masaüstü testi için ARAR_UI_TESTS=1 ayarlayın.')
class DesktopTests(unittest.TestCase):
    def setUp(self):
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
        self.temp.cleanup()

    def pump_until(self,condition,timeout=10):
        deadline=time.monotonic()+timeout
        while not condition() and time.monotonic()<deadline:
            self.root.update()
            time.sleep(.01)
        self.root.update()
        self.assertTrue(condition(),'Arayüz işlemi zamanında tamamlanmadı.')

    def test_review_while_next_page_is_analyzing(self):
        entered=threading.Event()
        def analyze(result,cancel):
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
        self.app._refresh()
        self.root.update()
        entered=threading.Event()
        def analyze(result,cancel):
            if result.index==0:
                entered.set()
                self.gate.wait(10)
            result.state='review' if result.index==0 else 'attachment'
            result.barcode='AFTER' if result.index==0 else ''
            return result
        with patch('arar.app.analyze_page',side_effect=analyze),patch('arar.app.messagebox.askyesno',return_value=True):
            self.app.analyze()
            self.pump_until(entered.is_set)
            self.app.barcode_var.set('MANUAL')
            self.app.cover_btn.invoke()
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
                checkbox=next(widget for widget in dialog.winfo_children()
                              if widget.winfo_class()=='TCheckbutton' and widget.cget('text')=='Kapak olarak işaretlerken onay sor')
                self.assertEqual(checkbox.instate(['selected']),not enabled)
                checkbox.invoke()
                save=next(widget for widget in dialog.winfo_children() if widget.winfo_class()=='TButton')
                self.assertLessEqual(save.winfo_y()+save.winfo_height(),dialog.winfo_height())
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
                checkbox=next(widget for widget in dialog.winfo_children()
                              if widget.winfo_class()=='TCheckbutton' and widget.cget('text')=='Tarama bittiğinde uyarı göster')
                self.assertEqual(checkbox.instate(['selected']),not enabled)
                checkbox.invoke()
                save=next(widget for widget in dialog.winfo_children() if widget.winfo_class()=='TButton')
                self.assertLessEqual(save.winfo_y()+save.winfo_height(),dialog.winfo_height())
                save.invoke()
                self.root.update()
                self.app.settings=Settings.load()
                self.assertEqual(self.app.settings.notify_analysis_done,enabled)

    def test_confirmation_updates_original_page_if_selection_changes(self):
        entered=threading.Event()
        def analyze(result,cancel):
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
