"""Install/remove an optional per-user Worker login entry; default is preview."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys


def render(kind, python, env_file, log_file):
    command = [str(python), '-m', 'media_dl.worker', '--env-file', str(env_file), '--log-file', str(log_file)]
    if kind == 'windows':
        text = subprocess.list2cmdline(command).replace('"', '""')
        return ('\' lark-media-dl managed startup\nCreateObject("WScript.Shell").Run "' + text + '", 0, False\n').encode('utf-8')
    if kind == 'macos':
        return plistlib.dumps({'Label': 'io.github.lark-media-dl', 'ProgramArguments': command,
                              'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 15})
    quote = lambda s: '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
    return ('[Unit]\nDescription=Personal media download Worker\nAfter=network-online.target\n\n'
            '[Service]\nExecStart=' + ' '.join(quote(s) for s in command) + '\nRestart=on-failure\nRestartSec=15\n\n'
            '[Install]\nWantedBy=default.target\n').encode('utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--remove', action='store_true')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    env_file = args.env_file.expanduser().resolve()
    if not env_file.is_file():
        parser.error('Configuration file does not exist')
    kind = 'windows' if sys.platform == 'win32' else 'macos' if sys.platform == 'darwin' else 'linux'
    python = root / '.venv' / ('Scripts/pythonw.exe' if kind == 'windows' else 'bin/python')
    if not python.is_file():
        parser.error('Install the package in .venv first')
    config = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'lark-media-dl'
    if kind == 'windows':
        target = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/Startup/lark-media-dl.vbs'
    elif kind == 'macos':
        target = Path.home() / 'Library/LaunchAgents/io.github.lark-media-dl.plist'
    else:
        target = Path.home() / '.config/systemd/user/lark-media-dl.service'
    manifest = config / 'startup-install.json'
    previous = json.loads(manifest.read_text()) if manifest.is_file() else None
    if target.exists() and (not previous or previous.get('path') != str(target) or
                           previous.get('sha256') != hashlib.sha256(target.read_bytes()).hexdigest()):
        parser.error('Existing startup entry is not an unchanged installation owned by this project')
    print(('Remove' if args.remove else 'Install'), target)
    if not args.apply:
        print('Preview only. Add --apply. This affects the optional Worker, not local CLI downloads.')
        return 0
    if args.remove:
        if kind == 'linux' and target.exists():
            subprocess.run(['systemctl', '--user', 'disable', '--now', 'lark-media-dl.service'], check=True)
        elif kind == 'macos' and target.exists():
            subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}', str(target)], check=False)
        if previous:
            target.unlink(missing_ok=True)
            manifest.unlink()
        print('Startup entry removed. On Windows, stop the existing Worker separately using its recorded PID.')
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    config.mkdir(parents=True, exist_ok=True)
    target.write_bytes(render(kind, python, env_file, config / 'worker.log'))
    manifest.write_text(json.dumps({'path': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}), encoding='utf-8')
    if kind == 'linux':
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', '--user', 'enable', '--now', 'lark-media-dl.service'], check=True)
    elif kind == 'macos':
        subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(target)], check=True)
    else:
        subprocess.run(['wscript.exe', str(target)], check=True)
    print('Installed. Check scripts/status.py and the cloud heartbeat; a file alone does not prove readiness.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
