"""Local bundle isolation and safe developer preparation."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import local_dependencies as dependencies
import prepare_local_libs as preparation


class DependencyTests(unittest.TestCase):
    def test_bundle_imports_and_native_operations_without_site_packages(self):
        result = subprocess.run(
            [sys.executable, '-S', '-B', '-c', preparation.VERIFY_CODE,
             str(dependencies.ROOT), str(dependencies.LIBS)],
            capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        origins = json.loads(result.stdout)
        self.assertEqual(set(origins), set(dependencies.MODULES))

    def test_missing_and_empty_bundle_cannot_fall_back_to_system_packages(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copy2(dependencies.ROOT / 'local_dependencies.py', root)
            code = "from local_dependencies import activate_local_dependencies; activate_local_dependencies()"
            for empty in (False, True):
                with self.subTest(empty=empty):
                    if empty:
                        (root / 'libs').mkdir()
                    result = subprocess.run([sys.executable, '-B', '-c', code], cwd=root,
                                            capture_output=True, text=True, encoding='utf-8')
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('setup_offline_libs.bat', result.stderr)
                    self.assertIn('libs', result.stderr)

    def test_incompatible_bundle_is_rejected_before_binary_imports(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copy2(dependencies.ROOT / 'local_dependencies.py', root)
            libs = root / 'libs'
            libs.mkdir()
            identity = dependencies.runtime_identity()
            identity['python'] = [3, 11]
            (libs / 'arar_bundle.json').write_text(json.dumps({'runtime': identity}), encoding='utf-8')
            result = subprocess.run([sys.executable, '-S', '-B', '-c',
                                    'from local_dependencies import activate_local_dependencies; activate_local_dependencies()'],
                                    cwd=root, capture_output=True, text=True, encoding='utf-8')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('3.11', result.stderr)
            self.assertIn('uyumlu', result.stderr)


class LaunchTests(unittest.TestCase):
    def run_launch(self,verify_error=None,source_error=None,wheels=False):
        with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
            root=Path(folder)
            if wheels:
                (root/'wheelhouse').mkdir()
                (root/'wheelhouse'/'local.whl').touch()
            stack.enter_context(patch.object(preparation,'ROOT',root))
            verify=stack.enter_context(patch.object(preparation,'verify_local_bundle',side_effect=verify_error))
            prepare=stack.enter_context(patch.object(preparation,'prepare',side_effect=source_error))
            stack.enter_context(patch.object(preparation.sys,'platform','linux'))
            run=stack.enter_context(patch.object(preparation.subprocess,'run'))
            run.return_value.returncode=0
            stack.enter_context(patch('builtins.print'))
            args=argparse.Namespace(from_installed=False,wheelhouse=None)
            if source_error:
                with self.assertRaisesRegex(ValueError,'İnternete bağlanılmadı'):
                    preparation.launch(args)
                run.assert_not_called()
            else:
                self.assertEqual(preparation.launch(args),0)
                run.assert_called_once_with([sys.executable,'-B',str(root/'main.py')],cwd=root)
            verify.assert_called_once()
            return prepare

    def test_ready_bundle_launches_without_installing(self):
        self.run_launch().assert_not_called()

    def test_missing_bundle_is_prepared_from_installed_packages(self):
        prepare=self.run_launch(verify_error=ValueError('missing'))
        self.assertTrue(prepare.call_args.args[0].from_installed)
        self.assertIsNone(prepare.call_args.args[0].wheelhouse)
        self.assertTrue(prepare.call_args.args[0].replace)

    def test_local_wheels_are_used_without_an_online_index(self):
        prepare=self.run_launch(verify_error=ValueError('missing'),wheels=True)
        self.assertFalse(prepare.call_args.args[0].from_installed)
        self.assertEqual(Path(prepare.call_args.args[0].wheelhouse).name,'wheelhouse')

    def test_unavailable_local_packages_do_not_launch_or_fetch_online(self):
        self.run_launch(verify_error=ValueError('missing'),source_error=ValueError('no local packages'))


class PreparationTests(unittest.TestCase):
    def test_existing_libs_is_not_modified_without_replace(self):
        with tempfile.TemporaryDirectory() as folder:
            libs = Path(folder) / 'libs'
            libs.mkdir()
            original = libs / 'keep.txt'
            original.write_text('existing', encoding='utf-8')
            with patch.object(preparation, 'LIBS', libs), patch.object(preparation.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, '--replace'):
                    preparation.prepare(argparse.Namespace(replace=False, from_installed=True, wheelhouse=None))
            run.assert_not_called()
            self.assertEqual(original.read_text(encoding='utf-8'), 'existing')

    def test_failed_validation_preserves_existing_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            libs = root / 'libs'
            libs.mkdir()
            (libs / 'keep.txt').write_text('existing', encoding='utf-8')
            with patch.object(preparation, 'ROOT', root), patch.object(preparation, 'LIBS', libs), \
                    patch.object(preparation, 'pinned_requirements', return_value={}), \
                    patch.object(preparation, 'copy_installed'), \
                    patch.object(preparation.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'verify')):
                with self.assertRaises(subprocess.CalledProcessError):
                    preparation.prepare(argparse.Namespace(replace=True, from_installed=True, wheelhouse=None))
            self.assertEqual((libs / 'keep.txt').read_text(encoding='utf-8'), 'existing')
            self.assertEqual(list(root.iterdir()), [libs])

    def test_successful_replace_keeps_old_bundle_as_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            libs = root / 'libs'
            libs.mkdir()
            (libs / 'keep.txt').write_text('existing', encoding='utf-8')
            def copy(packages, stage):
                (stage / 'new.txt').write_text('new', encoding='utf-8')
            with patch.object(preparation, 'ROOT', root), patch.object(preparation, 'LIBS', libs), \
                    patch.object(preparation, 'pinned_requirements', return_value={}), \
                    patch.object(preparation, 'copy_installed', side_effect=copy), \
                    patch.object(preparation.subprocess, 'run'), patch('builtins.print'):
                preparation.prepare(argparse.Namespace(replace=True, from_installed=True, wheelhouse=None))
            backup = next(root.glob('libs.backup-*'))
            self.assertEqual((backup / 'keep.txt').read_text(encoding='utf-8'), 'existing')
            self.assertEqual((libs / 'new.txt').read_text(encoding='utf-8'), 'new')


if __name__ == '__main__':
    unittest.main()
