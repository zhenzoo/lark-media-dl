"""Shared yt-dlp execution for YouTube, Bilibili and resolved X video."""
from pathlib import Path
import json
import subprocess
import sys
import shutil
from ..config import ffmpeg_path
from .bilibili import bili_anon_cookiejar
from .x import twitter_via_fxtwitter


def download(url: str, platform: str, outdir: Path, env: dict, *, audio=False,
             meta_only=False, quality='1080', cookies=None, browser=None) -> dict:
    proxy = env.get('MEDIA_DL_PROXY', env.get('HTTPS_PROXY', ''))
    flags = ['--no-playlist', '--no-progress', '--no-warnings', '--socket-timeout', '30',
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
    ffmpeg = ffmpeg_path(env)
    if ffmpeg:
        flags += ['--ffmpeg-location', ffmpeg]
    runtime = env.get('MEDIA_DL_JS_RUNTIME') or next((name for name in ('deno', 'node', 'bun', 'qjs') if shutil.which(name)), None)
    if runtime:
        flags += ['--js-runtimes', runtime]
    metadata = {}
    if platform == 'x':
        post = twitter_via_fxtwitter(url, proxy)
        if not post:
            raise RuntimeError('X 未解析出公开视频；当前不支持纯文字或图片帖')
        metadata = {'title': post['title'], 'uploader': post['author'], 'duration_sec': post['duration']}
        if meta_only:
            return {'meta': metadata, 'files': []}
        url = post['m3u8'] or post['direct_url']
        if not url:
            raise RuntimeError('X 视频没有可下载地址')
    if meta_only:
        flags += ['--skip-download', '--dump-single-json']
    else:
        outdir.mkdir(parents=True, exist_ok=True)
        flags += ['--no-overwrites', '--restrict-filenames', '-N', '8',
                  '-o', str(outdir / '%(title).80s-%(id)s.%(ext)s')]
        if audio:
            if not ffmpeg:
                raise RuntimeError('提取 MP3 需要 FFmpeg')
            flags += ['-x', '--audio-format', 'mp3', '-f', 'bestaudio/best']
        else:
            fmt = 'bv*+ba/b' if quality == 'best' else f'bv*[height<={quality}]+ba/b[height<={quality}]'
            flags += ['-f', fmt, '--merge-output-format', 'mp4']
    result = subprocess.run([sys.executable, '-m', 'yt_dlp', *flags, url],
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=7200)
    if result.returncode:
        raise RuntimeError('yt-dlp 下载失败：' + (result.stderr or result.stdout)[-1200:])
    if meta_only:
        info = json.loads(result.stdout)
        return {'meta': {'title': info.get('title'), 'uploader': info.get('uploader'),
                         'duration_sec': info.get('duration')}, 'files': []}
    files = [p for p in outdir.iterdir() if p.is_file() and p.suffix.lower() in
             {'.mp4', '.mkv', '.webm', '.mp3', '.m4a', '.ogg', '.wav', '.mov'}]
    if not files or (audio and any(p.suffix != '.mp3' for p in files)):
        raise RuntimeError('下载没有生成所请求的媒体文件')
    return {'meta': metadata, 'files': files}
