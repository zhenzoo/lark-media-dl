"""Portable local configuration. Secrets are never included in status output."""
from pathlib import Path
import os
from .media_output import find_ffmpeg


def config_dir() -> Path:
    root = os.environ.get('XDG_CONFIG_HOME')
    return (Path(root).expanduser() if root else Path.home() / '.config') / 'lark-media-dl'


def read_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def load_config(path: str | None = None) -> dict[str, str]:
    result = read_env(config_dir() / '.env')
    selected = path or os.environ.get('MEDIA_DL_ENV_FILE')
    if selected:
        chosen = Path(selected).expanduser()
        if not chosen.is_file():
            raise ValueError('指定的配置文件不存在')
        result.update(read_env(chosen))
    else:
        result.update(read_env(Path.cwd() / '.env'))
    result.update(os.environ)
    return result


def ffmpeg_path(env: dict) -> str | None:
    return find_ffmpeg(env)


def redact(message: str, env: dict) -> str:
    for key, value in env.items():
        if any(word in key.upper() for word in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'PROXY')) and len(value) > 5:
            message = message.replace(value, '[redacted]')
    return message[-2000:]
