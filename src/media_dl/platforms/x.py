"""Resolve public X posts with FxTwitter and save every media item, not just the first video."""
from pathlib import Path
import re

UA = "Mozilla/5.0"


def twitter_via_fxtwitter(url: str, proxy: str | None):
    """Resolve the whole post: text, author and all media in posting order.
    Returns {id, author, text, title, media: [{type, m3u8, direct_url, url, duration, width, height}]}
    or None when FxTwitter has no such post. Videos prefer m3u8 (HLS, parallel fragments) and fall
    back to the highest-bitrate MP4; photos use the pbs original (?name=orig)."""
    import requests
    m = re.search(r"(?:x\.com|twitter\.com)/([^/?#]+)/status/(\d+)", url)
    if m:
        user, sid = m.group(1), m.group(2)
    else:
        m2 = re.search(r"status/(\d+)", url)
        sid, user = (m2.group(1) if m2 else None), "i"
    if not sid:
        return None
    api = f"https://api.fxtwitter.com/{user}/status/{sid}"
    # The FxTwitter API is usually reachable directly; only the media CDNs need the proxy.
    j = None
    for use_proxy in (False, True):
        try:
            s = requests.Session(); s.trust_env = False
            proxies = ({"http": proxy, "https": proxy} if (use_proxy and proxy) else None)
            r = s.get(api, timeout=30, proxies=proxies, headers={"User-Agent": UA})
            j = r.json()
            if j:
                break
        except Exception:
            continue
    tw = (j or {}).get("tweet") or {}
    if not tw:
        return None
    return {"id": sid, "author": (tw.get("author") or {}).get("screen_name"),
            "text": (tw.get("text") or "").strip(),
            "title": (tw.get("text") or f"tweet-{sid}").strip().split("\n")[0][:80],
            "media": media_items(tw)}


def media_items(tw: dict) -> list[dict]:
    """media.all keeps posting order and mixes video/photo/gif; older payloads only have videos/photos."""
    media = tw.get("media") or {}
    items = media.get("all") or ((media.get("videos") or []) + (media.get("photos") or []))
    out = []
    for v in items:
        kind = v.get("type") or ("video" if v.get("variants") or v.get("formats") else "photo")
        if kind in ("video", "gif"):
            m3u8 = None
            for fmt in (v.get("formats") or []):
                if fmt.get("container") == "m3u8" and fmt.get("url"):
                    m3u8 = fmt["url"]; break
            if not m3u8:
                for var in (v.get("variants") or []):
                    if "m3u8" in (var.get("content_type", "") + var.get("url", "")):
                        m3u8 = var.get("url"); break
            out.append({"type": kind, "m3u8": m3u8, "direct_url": v.get("url"), "duration": v.get("duration"),
                        "width": v.get("width"), "height": v.get("height")})
        else:
            u = v.get("url") or ""
            if u and "pbs.twimg.com" in u and "name=" not in u:
                u = u.split("?")[0] + "?name=orig"
            out.append({"type": "photo", "url": u, "width": v.get("width"), "height": v.get("height")})
    return out


def fetch_photo(url: str, stem: Path, proxy: str | None) -> Path:
    """pbs.twimg.com usually needs the media proxy; try it first, then direct."""
    import requests
    last = None
    routes = ([{"http": proxy, "https": proxy}] if proxy else []) + [{"http": None, "https": None}]
    for proxies in routes:
        try:
            with requests.Session() as session:
                session.trust_env = False
                r = session.get(url, headers={"User-Agent": UA}, proxies=proxies, timeout=60)
            if r.status_code == 200 and r.content:
                kind = r.headers.get("Content-Type", "")
                suffix = ".png" if "png" in kind else ".webp" if "webp" in kind else ".gif" if "gif" in kind else ".jpg"
                path = stem.with_suffix(suffix)
                path.write_bytes(r.content)
                return path
            last = RuntimeError(f"HTTP {r.status_code}")
        except requests.RequestException as error:
            last = error
    raise RuntimeError(f"X 图片下载失败：{last}")


def download(url: str, outdir: Path, env: dict, *, audio=False, meta_only=False,
             quality='1080', cookies=None, browser=None) -> dict:
    proxy = env.get('MEDIA_DL_PROXY', env.get('HTTPS_PROXY', '')) or None
    post = twitter_via_fxtwitter(url, proxy)
    if not post:
        raise RuntimeError('X 未解析出该推文（已删除、受限或 FxTwitter 不可达）')
    videos = [m for m in post['media'] if m['type'] in ('video', 'gif')]
    photos = [m for m in post['media'] if m['type'] == 'photo']
    meta = {'title': post['title'], 'uploader': post['author'], 'text': post['text'],
            'video_count': len(videos), 'photo_count': len(photos),
            'duration_sec': videos[0].get('duration') if videos else None}
    if meta_only:
        return {'meta': meta, 'files': []}
    if audio and not videos:
        raise RuntimeError('该推文没有视频，无法提取音频')
    from .ytdlp import download as yt_download
    outdir.mkdir(parents=True, exist_ok=True)
    base = f"x-{post['id']}"
    files: list[Path] = []
    for index, video in enumerate(videos, 1):
        source = video.get('m3u8') or video.get('direct_url')
        if not source:
            raise RuntimeError(f'第 {index} 个视频没有可下载地址')
        name = f'{base}-{index:02d}' if len(videos) > 1 else base
        files += yt_download(source, 'x', outdir, env, audio=audio, meta_only=False, quality=quality,
                             cookies=cookies, browser=browser, name=name)['files']
    if not audio:
        for index, photo in enumerate(photos, 1):
            files.append(fetch_photo(photo['url'], outdir / f'{base}-{index:02d}', proxy))
        if post['text']:
            text = outdir / f'{base}.txt'
            text.write_text(f"@{post['author']}\n{url}\n\n{post['text']}\n", encoding='utf-8')
            files.append(text)
    if not files:
        raise RuntimeError('该推文没有可保存的正文、图片或视频')
    return {'meta': meta, 'files': files}
