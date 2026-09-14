"""Validate yt-dlp's final artifact instead of treating stream fragments as a result."""
import json
from pathlib import Path
import shutil
import subprocess


FINAL_TEMPLATE = 'after_move:%(.{filepath,acodec,vcodec,requested_formats})j'


def find_ffmpeg(env):
    binary = env.get('FFMPEG_BINARY') or shutil.which('ffmpeg')
    if binary:
        return binary
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return None


def require_ffmpeg(env):
    binary = find_ffmpeg(env)
    try:
        if binary and subprocess.run([binary, '-version'], capture_output=True, timeout=15).returncode == 0:
            return binary
    except (OSError, subprocess.SubprocessError):
        pass
    raise RuntimeError('FFmpeg 不可用：请安装 FFmpeg 或 imageio-ffmpeg；不能把分开的音视频当作下载完成')


def final_media(manifest, directory, ffmpeg, audio=False):
    manifest = Path(manifest)
    rows = [json.loads(line) for line in manifest.read_text(encoding='utf-8').splitlines() if line.strip()] if manifest.is_file() else []
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise RuntimeError('没有唯一的后处理完成记录，音视频可能尚未合并')
    info = rows[0]
    file = Path(info.get('filepath') or '').resolve()
    if not file.is_relative_to(Path(directory).resolve()) or not file.is_file() or file.stat().st_size == 0:
        raise RuntimeError('下载完成记录没有指向有效成片')
    if file.suffix.lower() != ('.mp3' if audio else '.mp4'):
        raise RuntimeError('下载结果不是所请求的 MP3 音频或 MP4 视频')
    formats = info.get('requested_formats') or []
    expects_audio = audio or info.get('acodec') not in (None, 'none', 'NA') or any(
        part.get('vcodec') == 'none' or part.get('acodec') not in (None, 'none', 'NA')
        for part in formats if isinstance(part, dict))
    args = [ffmpeg, '-nostdin', '-v', 'error', '-i', str(file), '-t', '0.1']
    if not audio:
        args += ['-map', '0:v:0']
    if expects_audio:
        args += ['-map', '0:a:0']
    args += ['-f', 'null', '-']
    checked = subprocess.run(args, capture_output=True, timeout=60)
    if checked.returncode:
        raise RuntimeError('成片校验失败：缺少应有的视频或音轨，不能交付分离文件')
    return [file]
