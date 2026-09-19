"""Shared yt-dlp execution for YouTube, Bilibili, LinkedIn and each resolved X video URL."""
from pathlib import Path
import json
import subprocess
import sys
import shutil
from ..config import ffmpeg_path
from ..media_output import FINAL_TEMPLATE, final_media, require_ffmpeg
from .bilibili import bili_anon_cookiejar


def download(url: str, platform: str, outdir: Path, env: dict, *, audio=False,
             meta_only=False, quality='1080', cookies=None, browser=None, name=None) -> dict:
    """``name`` fixes the output stem (needed when one post yields several files); the
    finished-file manifest is per call so multiple runs into one directory stay separate."""
    proxy = env.get('MEDIA_DL_PROXY', env.get('HTTPS_PROXY', ''))
    flags = ['--ignore-config', '--no-playlist', '--no-progress', '--no-warnings', '--socket-timeout', '30',
             '--retries', '3', '--fragment-retries', '3', '--proxy', proxy,
             '--user-agent', 'Mozilla/5.0']
    if cookies:
        flags += ['--cookies', str(Path(cookies).expanduser())]
    elif browser:
        flags += ['--cookies-from-browser', browser]
    elif platform == 'bilibili':
        flags += ['--cookies', bili_anon_cookiejar()]
    if platform == 'bilibili':
        flags += ['--add-header', 'Origin:https://www.bilibili.com',
                  '--add-header', 'Referer:https://www.bilibili.com/']
    ffmpeg = ffmpeg_path(env) if meta_only else require_ffmpeg(env)
    if ffmpeg:
        flags += ['--ffmpeg-location', ffmpeg]
    runtime = env.get('MEDIA_DL_JS_RUNTIME') or next((name for name in ('deno', 'node', 'bun', 'qjs') if shutil.which(name)), None)
    if runtime:
        flags += ['--js-runtimes', runtime]
    metadata = {}
    if meta_only:
        flags += ['--skip-download', '--dump-single-json']
    else:
        outdir.mkdir(parents=True, exist_ok=True)
        manifest = outdir / (f'.final-media-{name}.jsonl' if name else '.final-media.jsonl')
        template = f'{name}.%(ext)s' if name else '%(title).80s-%(id)s.%(ext)s'
        flags += ['--no-overwrites', '--restrict-filenames', '-N', '8',
                  '--no-simulate', '--print-to-file', FINAL_TEMPLATE, str(manifest),
                  '-o', str(outdir / template)]
        if audio:
            if not ffmpeg:
                raise RuntimeError('提取 MP3 需要 FFmpeg')
            flags += ['-x', '--audio-format', 'mp3', '-f', 'bestaudio/best']
        else:
            fmt = 'bv*+ba/b' if quality == 'best' else f'bv*[height<={quality}]+ba/b[height<={quality}]'
            flags += ['-f', fmt, '--merge-output-format', 'mp4', '--remux-video', 'mp4']
    result = subprocess.run([sys.executable, '-m', 'yt_dlp', *flags, url],
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=7200)
    if result.returncode:
        raise RuntimeError('yt-dlp 下载失败：' + (result.stderr or result.stdout)[-1200:])
    if meta_only:
        info = json.loads(result.stdout)
        return {'meta': {'title': info.get('title'), 'uploader': info.get('uploader'),
                         'duration_sec': info.get('duration')}, 'files': []}
    files = final_media(manifest, outdir, ffmpeg, audio)
    return {'meta': metadata, 'files': files}
