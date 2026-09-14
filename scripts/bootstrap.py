"""Create this checkout's isolated Python environment; preview unless --apply."""
import argparse
from pathlib import Path
import subprocess
import sys
import venv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--oss', action='store_true', help='Install optional OSS dependency')
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error('Install Python 3.10+ from https://www.python.org/downloads/ first')
    root = Path(__file__).resolve().parents[1]
    environment = root / '.venv'
    python = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    print('Environment:', environment)
    print('Package:', str(root) + ('[oss]' if args.oss else ''))
    print('No Feishu, OSS, browser login or system startup configuration is required by default.')
    if not args.apply:
        print('Preview only. Add --apply to install.')
        return 0
    if environment.exists() and not python.is_file():
        parser.error('Existing .venv is not a usable environment; inspect it before continuing')
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    subprocess.run([str(python), '-m', 'pip', 'install', '-e', str(root) + ('[oss]' if args.oss else '')], check=True)
    subprocess.run([str(python), '-m', 'media_dl.doctor', '--json'], check=True)
    print('Installed. Register a Skill with scripts/install_skill.py, or run the media-dl command in .venv.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
