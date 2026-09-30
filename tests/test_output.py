"""Private bounded output remains independent of transport."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from test_tools import load_tools


class OutputTests(unittest.TestCase):
    def setUp(self):
        load_tools()
        self.output = importlib.import_module('tool_fixture_plugin.output')
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        module = types.ModuleType('hermes_constants')
        module.get_hermes_home = lambda: self.home
        stub = patch.dict(sys.modules, {'hermes_constants': module})
        stub.start()
        self.addCleanup(stub.stop)

    def artifact(self, text):
        self.assertLess(len(text.encode()), 18000)
        path = Path(text.split('Complete UTF-8 text: ', 1)[1].splitlines()[0])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        return path

    def test_small_and_utf8_complete_profile_artifacts(self):
        for text in ('', 'é' * 8000):
            self.assertEqual(self.output._bounded_output(text), text)
        paths = []
        base = self.home
        for profile in ('a', 'b', 'a'):
            self.home = base / profile
            self.home.mkdir(exist_ok=True)
            raw = '€' * 10001 + '\n'
            result = self.output._bounded_output(raw)
            path = self.artifact(result)
            self.assertEqual(path.read_bytes(), raw.encode())
            self.assertTrue(path.is_relative_to(self.home))
            self.assertNotIn('�', result)
            paths.append(path)
        self.assertEqual(len(set(paths)), 3)

    def test_collision_does_not_overwrite(self):
        store = self.home / 'fulcra-output'
        store.mkdir(mode=0o700)
        existing = store / ('result-' + 'a' * 32 + '.txt')
        existing.write_text('keep')
        with patch.object(self.output.secrets, 'token_hex', side_effect=['a' * 32, 'b' * 32]):
            self.assertEqual(self.artifact(self.output._bounded_output('x' * 20000)).read_text(), 'x' * 20000)
        self.assertEqual(existing.read_text(), 'keep')

    def test_insecure_or_swapped_directory_and_failed_write(self):
        store = self.home / 'fulcra-output'
        outside = self.home / 'outside'
        outside.mkdir()
        store.symlink_to(outside, target_is_directory=True)
        self.assertTrue(self.output._bounded_output('x' * 20000).startswith('Error:'))
        self.assertEqual(list(outside.iterdir()), [])
        store.unlink()
        store.mkdir(mode=0o755)
        self.assertTrue(self.output._bounded_output('x' * 20000).startswith('Error:'))
        store.chmod(0o700)
        with patch.object(self.output.os, 'fchmod', side_effect=OSError('full')):
            self.assertTrue(self.output._bounded_output('x' * 20000).startswith('Error:'))
        self.assertEqual(list(store.iterdir()), [])
        real_open = os.open
        def swap(path, flags, mode=0o777, *, dir_fd=None):
            if flags & os.O_CREAT:
                store.rename(self.home / 'moved')
                store.symlink_to(outside, target_is_directory=True)
                self.assertIsNotNone(dir_fd)
                self.assertTrue(flags & os.O_EXCL)
            return real_open(path, flags, mode, dir_fd=dir_fd)
        with patch.object(self.output.os, 'open', side_effect=swap):
            self.assertTrue(self.output._bounded_output('x' * 20000).startswith('Error:'))
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(list((self.home / 'moved').iterdir()), [])
