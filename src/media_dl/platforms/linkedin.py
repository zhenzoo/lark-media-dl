"""LinkedIn public posts: text, author and images from the public page; video via yt-dlp.

No LinkedIn login, cookie or API key. The public post page is fetched through the
configured media proxy first (linkedin.com is often unreachable directly), then
directly. Only the main ``<article>`` block is parsed: the page also embeds a dozen
related posts whose images and text must never be mixed into the result.
"""
from pathlib import Path
import html
import re
import subprocess

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')


def parse_page(page: str) -> dict | None:
    """Pure parser: main post block -> text / author / images / has_video. None if no main post."""
    articles = list(re.finditer(r'<article[^>]*>', page))
    main = None
    for index, match in enumerate(articles):
        if 'related-posts' in match.group(0) or 'Reshared' in match.group(0):
            continue
        end = articles[index + 1].start() if index + 1 < len(articles) else len(page)
        main = page[match.start():end]
        break
    if main is None:
        return None

    def clean(fragment: str) -> str:
        fragment = re.sub(r'<br\s*/?>', '\n', fragment)
        return html.unescape(re.sub(r'<(?!br)[^>]+>', '', fragment)).strip()

    # Post body is marked main-feed-activity-card__commentary; the same paragraph class is reused
    # for comments (comment__text), which must not leak into the saved text.
    segments = re.findall(r'<p([^>]*attributed-text-segment-list__content[^>]*)>(.*?)</p>', main, re.S)
    body = [clean(body) for attrs, body in segments if 'main-feed-activity-card__commentary' in attrs]
    if not body:
        body = [clean(body) for attrs, body in segments if 'comment__text' not in attrs]
    paragraphs = body
    author = re.search(r'data-tracking-control-name="public_post_feed-actor-name"[^>]*>(.*?)</a>', main, re.S)
    images: list[str] = []
    block = re.search(r'data-test-id="feed-images-content"(.*?)</ul>', main, re.S)
    for url in re.findall(r'data-delayed-url="([^"]+)"', block.group(1) if block else ''):
        url = html.unescape(url)
        if 'feedshare-' in url and url not in images:
            images.append(url)
    if not images:  # single-image posts sometimes only expose og:image
        og = re.search(r'<meta property="og:image" content="([^"]+)"', page)
        if og and 'feedshare-' in og.group(1):
            images.append(html.unescape(og.group(1)))
    return {'text': '\n\n'.join(p for p in paragraphs if p),
            'author': clean(author.group(1)) if author else None,
            'images': images,
            'has_video': bool(re.search(r'<video\b|videocover-|/playlist/vid/', main))}


def _routes(proxy: str | None) -> list[dict]:
    routes = [{'http': proxy, 'https': proxy}] if proxy else []
    return routes + [{'http': None, 'https': None}]


def fetch_page(url: str, proxy: str | None) -> dict:
    import requests
    for proxies in _routes(proxy):
        try:
            with requests.Session() as session:
                session.trust_env = False
                response = session.get(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'},
                                       proxies=proxies, timeout=45, allow_redirects=True)
            if response.status_code == 200 and '<article' in response.text:
                post = parse_page(response.text)
                if post:
                    return post
        except requests.RequestException:
            continue
    raise RuntimeError('无法读取 LinkedIn 公开帖页面；检查代理（linkedin.com 通常需要代理）、链接是否为单条帖子或内容是否需要登录')


def fetch_image(url: str, proxy: str | None, target: Path) -> Path:
    import requests
    last = None
    for proxies in reversed(_routes(proxy)):  # licdn CDN is usually reachable directly; proxy as fallback
        try:
            with requests.Session() as session:
                session.trust_env = False
                response = session.get(url, headers={'User-Agent': UA, 'Referer': 'https://www.linkedin.com/'},
                                       proxies=proxies, timeout=60)
            if response.status_code == 200 and response.content:
                kind = response.headers.get('Content-Type', '')
                suffix = '.png' if 'png' in kind else '.webp' if 'webp' in kind else '.gif' if 'gif' in kind else '.jpg'
                path = target.with_suffix(suffix)
                path.write_bytes(response.content)
                return path
            last = RuntimeError(f'HTTP {response.status_code}')
        except requests.RequestException as error:
            last = error
    raise RuntimeError(f'LinkedIn 图片下载失败：{last}')


def extract_mp3(video: Path, ffmpeg: str) -> Path:
    """LinkedIn has no separate audio stream, so audio comes from the finished MP4.
    Many LinkedIn clips are silent; report that instead of a codec error."""
    probe = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-i', str(video), '-t', '0.1',
                            '-map', '0:a:0', '-f', 'null', '-'], capture_output=True, timeout=60)
    if probe.returncode:
        raise RuntimeError('该 LinkedIn 视频没有音轨（纯画面短片），无法提取 MP3')
    target = video.with_suffix('.mp3')
    result = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-i', str(video), '-vn',
                             '-codec:a', 'libmp3lame', '-q:a', '2', str(target)], capture_output=True, timeout=1800)
    if result.returncode or not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError('FFmpeg 提取 MP3 失败：' + result.stderr.decode('utf-8', 'ignore')[-400:])
    return target


def post_id(url: str) -> str:
    match = re.search(r'-(\d{15,})(?:-[A-Za-z0-9_-]+)?/?(?:\?|$)', url) or re.search(r'(\d{15,})', url)
    return match.group(1) if match else 'post'


def download(url: str, outdir: Path, env: dict, *, audio=False, meta_only=False,
             quality='1080', cookies=None, browser=None) -> dict:
    proxy = env.get('MEDIA_DL_PROXY', env.get('HTTPS_PROXY', '')) or None
    post = fetch_page(url, proxy)
    first_line = next((line.strip() for line in post['text'].splitlines() if line.strip()), '')
    meta = {'title': first_line[:80] or post['author'] or 'LinkedIn post', 'uploader': post['author'],
            'text': post['text'], 'image_count': len(post['images']), 'has_video': post['has_video']}
    if meta_only:
        return {'meta': meta, 'files': []}
    outdir.mkdir(parents=True, exist_ok=True)
    base = f'linkedin-{post_id(url)}'
    files: list[Path] = []
    if post['has_video']:
        from ..media_output import require_ffmpeg
        from .ytdlp import download as yt_download
        # LinkedIn formats carry no height metadata, so a height filter would match nothing;
        # 'best' picks the higher-bitrate rendition (LinkedIn tops out around 720p anyway).
        video = Path(yt_download(url, 'linkedin', outdir, env, audio=False, meta_only=False,
                                 quality='best', cookies=cookies, browser=browser)['files'][0])
        files.append(extract_mp3(video, require_ffmpeg(env)) if audio else video)
    elif audio:
        raise RuntimeError('该 LinkedIn 帖没有视频，无法提取音频')
    if not audio:
        for index, image in enumerate(post['images'], 1):
            files.append(fetch_image(image, proxy, outdir / f'{base}-{index:02d}'))
        if post['text']:
            header = f"{post['author'] or 'LinkedIn'}\n{url}\n\n"
            text = outdir / f'{base}.txt'
            text.write_text(header + post['text'] + '\n', encoding='utf-8')
            files.append(text)
    if not files:
        raise RuntimeError('该 LinkedIn 帖没有可保存的正文、图片或视频；PDF 文档帖当前不支持')
    return {'meta': meta, 'files': files}
