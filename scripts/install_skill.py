"""Register the Skill for a user-selected agent without replacing existing skills."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', choices=['codex', 'claude', 'kimi'], required=True)
    parser.add_argument('--home', type=Path, help='Explicit agent home; required for Kimi or a non-default profile')
    parser.add_argument('--python', type=Path, help='Installed package interpreter; default this checkout .venv')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    home = args.home.expanduser() if args.home else Path.home() / ('.agents' if args.agent == 'codex' else '.claude')
    if args.agent == 'kimi' and args.home is None:
        parser.error('Inspect the user\'s Kimi installation, then pass its --home explicitly')
    target = home / 'skills' / 'media-dl'
    manifest = target / '.lark-media-dl-install.json'
    if not args.uninstall:
        for skill in (home / 'skills').glob('*/SKILL.md'):
            if skill.parent == target:
                continue
            if re.search(r'^name:\s*[\"\x27]?media-dl[\"\x27]?\s*$', skill.read_text(encoding='utf-8'), re.M):
                parser.error('Another media-dl Skill already exists at ' + str(skill.parent))
    python = (args.python or root / '.venv' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')).resolve()
    files = {'SKILL.md': (root / 'skills/media-dl/SKILL.md').read_text(encoding='utf-8'),
             'scripts/run.py': 'import subprocess,sys\nraise SystemExit(subprocess.call([' + repr(str(python)) + ", '-m', 'media_dl', *sys.argv[1:]]))\n"}
    previous = json.loads(manifest.read_text(encoding='utf-8')) if manifest.is_file() else None
    if target.exists() and (not previous or previous.get('owner') != 'lark-media-dl'):
        parser.error('Existing media-dl Skill belongs to another installation; preserve it and choose a separate agent home')
    if previous:
        for name, digest in previous['files'].items():
            file = target / name
            if not file.resolve().is_relative_to(target.resolve()):
                parser.error('Invalid installer manifest path')
            if file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest() != digest:
                parser.error('Installed Skill has user edits; inspect before replacing or removing it')
    print(('Remove' if args.uninstall else 'Install'), target)
    if not args.apply:
        print('Preview only. Add --apply to proceed.')
        return 0
    if args.uninstall:
        if not previous:
            return 0
        # Delete only exact tracked installer-owned files after hash verification.
        for name in previous['files']:
            (target / name).unlink(missing_ok=True)
        manifest.unlink()
        for folder in (target / 'scripts', target):
            try:
                folder.rmdir()
            except OSError:
                pass  # Preserve any files added by the user.
        return 0
    if not python.is_file():
        parser.error('Install the package first with scripts/bootstrap.py --apply')
    hashes = {}
    for name, text in files.items():
        file = target / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding='utf-8', newline='\n')
        hashes[name] = hashlib.sha256(file.read_bytes()).hexdigest()
    manifest.write_text(json.dumps({'owner': 'lark-media-dl', 'files': hashes}, indent=2), encoding='utf-8')
    print('Registered. Open a new agent session to refresh skill discovery.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
