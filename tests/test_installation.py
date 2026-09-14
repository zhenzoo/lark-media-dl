import contextlib
import importlib.util
import io
import json
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallationTests(unittest.TestCase):
    def test_registration_is_repeatable_and_uninstall_preserves_extra_files(self):
        install = script('install_skill')
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            args = ['--agent', 'codex', '--home', tmp, '--python', sys.executable, '--apply']
            self.assertEqual(install.main(args), 0)
            self.assertEqual(install.main(args), 0)
            target = Path(tmp) / 'skills/media-dl'
            (target / 'my-note.txt').write_text('keep me')
            self.assertEqual(install.main(args + ['--uninstall']), 0)
            self.assertEqual((target / 'my-note.txt').read_text(), 'keep me')
            self.assertFalse((target / 'SKILL.md').exists())

    def test_installer_refuses_user_edits_and_existing_skill(self):
        install = script('install_skill')
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            args = ['--agent', 'codex', '--home', tmp, '--python', sys.executable, '--apply']
            install.main(args)
            file = Path(tmp) / 'skills/media-dl/SKILL.md'
            file.write_text('user replacement', encoding='utf-8')
            with self.assertRaises(SystemExit):
                install.main(args)
            with self.assertRaises(SystemExit):
                install.main(args + ['--uninstall'])
            self.assertEqual(file.read_text(), 'user replacement')

    def test_same_named_skill_in_another_folder_is_preserved(self):
        install = script('install_skill')
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()):
            old = Path(tmp) / 'skills/existing/SKILL.md'
            old.parent.mkdir(parents=True)
            old.write_text('---\nname: media-dl\n---\nExisting')
            with self.assertRaises(SystemExit):
                install.main(['--agent', 'codex', '--home', tmp, '--apply'])
            self.assertTrue(old.exists())

    def test_startup_preserves_paths_with_spaces(self):
        startup = script('startup')
        args = ['/opt/My Tools/python', '/home/A B/my.env', '/home/A B/log.txt']
        mac = plistlib.loads(startup.render('macos', *args))
        self.assertEqual(mac['ProgramArguments'][0], args[0])
        self.assertIn(args[1], mac['ProgramArguments'])
        linux = startup.render('linux', *args).decode()
        self.assertIn('"/home/A B/my.env"', linux)
        windows = startup.render('windows', *args).decode()
        self.assertIn('""/opt/My Tools/python""', windows)
        self.assertIn(', 0, False', windows)


if __name__ == '__main__':
    unittest.main()
