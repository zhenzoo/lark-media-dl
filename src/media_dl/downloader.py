"""One download contract for the CLI, the Skill and the background Worker."""
from pathlib import Path
from urllib.parse import urlparse
import tempfile
from .results import save_loose_files

DOMAINS = {
    'youtube': ('youtube.com', 'youtu.be'),
    'bilibili': ('bilibili.com', 'b23.tv'),
    'xiaohongshu': ('xiaohongshu.com', 'xhslink.com'),
    'x': ('x.com', 'twitter.com', 'fxtwitter.com', 'vxtwitter.com'),
    'threads': ('threads.com', 'threads.net'),
    'linkedin': ('linkedin.com', 'lnkd.in'),
}


def detect_platform(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or ''
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('请提供受支持平台的 HTTPS 单帖或视频链接')
    for platform, domains in DOMAINS.items():
        if any(host == d or host.endswith('.' + d) for d in domains):
            return platform
    raise ValueError('当前支持 YouTube、Bilibili、小红书、X、Threads 和 LinkedIn')


def download(url: str, env: dict, *, outdir=None, audio=False, meta_only=False,
             quality='1080', cookies=None, browser=None, heartbeat=lambda: None) -> dict:
    platform = detect_platform(url)
    quality = 'best' if quality == 'max' else quality
    if quality != 'best' and (not quality.isdigit() or int(quality) <= 0):
        raise ValueError('画质使用 best 或 1080、720、480 等正整数')
    output = Path(outdir or env.get('MEDIA_DL_OUTPUT_DIR') or Path.home() / 'Downloads').expanduser().resolve()
    cookies = cookies or env.get(f'MEDIA_DL_{platform.upper()}_COOKIES')
    with tempfile.TemporaryDirectory(prefix='lark-media-dl-') as tmp:
        scratch = Path(tmp)
        if platform == 'threads':
            from .platforms.threads import ThreadsClient, metadata
            client = ThreadsClient(env, heartbeat)
            post = client.fetch_post(url)
            result = {'meta': metadata(post), 'files': [] if meta_only else
                      client.download(post, url, scratch, quality, audio_only=audio)}
        elif platform == 'x':
            from .platforms.x import download as x_download
            result = x_download(url, scratch, env, audio=audio, meta_only=meta_only,
                                quality=quality, cookies=cookies, browser=browser)
        elif platform == 'linkedin':
            from .platforms.linkedin import download as linkedin_download
            result = linkedin_download(url, scratch, env, audio=audio, meta_only=meta_only,
                                       quality=quality, cookies=cookies, browser=browser)
        elif platform == 'xiaohongshu':
            if browser:
                raise ValueError('小红书当前请用 --cookies 指定 Netscape Cookie 文件')
            from .platforms.xiaohongshu import download as xhs_download
            result = xhs_download(url, scratch, env, audio=audio, meta_only=meta_only, cookies=cookies)
        else:
            from .platforms.ytdlp import download as yt_download
            result = yt_download(url, platform, scratch, env, audio=audio, meta_only=meta_only,
                                 quality=quality, cookies=cookies, browser=browser)
        final = {'ok': True, 'platform': platform, 'url': url, 'meta': result.get('meta', {}),
                 'mode': 'meta-only' if meta_only else ('audio' if audio else 'post')}
        if not meta_only:
            files = [Path(p).resolve() for p in result['files']]
            if not files or any(not p.is_file() or not p.is_relative_to(scratch.resolve()) for p in files):
                raise RuntimeError('下载模块没有返回有效的完成文件')
            final.update(files=save_loose_files(files, output), outdir=str(output))
        return final
