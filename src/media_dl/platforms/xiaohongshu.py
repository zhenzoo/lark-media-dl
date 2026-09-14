"""Xiaohongshu public-page parsing with optional TikHub video resolution."""
import json,re
from pathlib import Path
from http.cookiejar import MozillaCookieJar
import requests
import subprocess
from urllib.parse import urlparse
from ..config import ffmpeg_path
UA = "Mozilla/5.0"


def tikhub_note(url, env):
    key = env.get('TIKHUB_API_KEY')
    if not key:
        return None
    base = env.get('TIKHUB_BASE', 'https://api.tikhub.dev').rstrip('/')
    if not base.startswith('https://'):
        raise ValueError('TikHub API 地址必须是 HTTPS')
    with requests.Session() as session:
        session.trust_env = False
        def get(path, params):
            r = session.get(base + path, params=params, headers={'Authorization': 'Bearer ' + key}, timeout=60)
            r.raise_for_status()
            payload = r.json()
            if payload.get('code') != 200:
                raise RuntimeError('TikHub 未返回笔记详情')
            return payload.get('data') or {}
        data = get('/api/v1/xiaohongshu/web/get_note_id_and_xsec_token', {'share_text': url})
        nid = data.get('note_id') or data.get('noteId')
        token = data.get('xsec_token') or data.get('xsecToken')
        if not nid:
            return None
        data = get('/api/v1/xiaohongshu/web_v3/fetch_note_detail', {'note_id': nid, 'xsec_token': token}) if token else get(
            '/api/v1/xiaohongshu/app_v2/get_video_note_detail', {'note_id': nid})
        # Preserve structured note fields when the endpoint returns a web note.
        def find(value):
            if isinstance(value, dict):
                if value.get('video') and _xhs_pick_video_stream(value)[1]:
                    return value
                for child in value.values():
                    found = find(child)
                    if found:
                        return found
            elif isinstance(value, list):
                for child in value:
                    found = find(child)
                    if found:
                        return found
            return None
        note = find(data)
        if note:
            return {**note, 'type': 'video'}
        blob = json.dumps(data, ensure_ascii=False)
        urls = list(dict.fromkeys(re.findall(r'https?://[^"\\]+?(?:\.mp4|sns-video[^"\\]+)', blob)))
        if not urls:
            return None
        def field(name):
            match = re.search(r'"' + name + r'"\s*:\s*("(?:\\.|[^"\\])*")', blob)
            return json.loads(match.group(1)) if match else ''
        return {'type': 'video', 'title': field('title') or field('display_title'), 'desc': field('desc'),
                'video': {'media': {'stream': {'h264': [{'masterUrl': urls[0], 'backupUrls': urls[1:]}]}}}}


def fetch_asset(url, target, env, kind):
    parsed = urlparse(url)
    host = parsed.hostname or ''
    if (parsed.scheme not in ('https', 'http') or parsed.username or parsed.password or
            not any(host == d or host.endswith('.' + d) for d in ('xhscdn.com', 'xhsimg.com', 'xiaohongshu.com'))):
        raise RuntimeError('小红书返回了未支持的媒体地址')
    with requests.Session() as session:
        session.trust_env = False
        proxy = env.get('MEDIA_DL_PROXY', '')
        if proxy:
            session.proxies.update(http=proxy, https=proxy)
        # CDN redirects must be checked again rather than following an arbitrary host.
        with session.get(url, headers={'User-Agent': UA, 'Referer': 'https://www.xiaohongshu.com/'},
                         timeout=(15, 90), stream=True, allow_redirects=False) as response:
            if response.status_code != 200:
                raise RuntimeError('小红书媒体请求失败：HTTP ' + str(response.status_code))
            content_type = response.headers.get('Content-Type', '').split(';')[0]
            allowed = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp',
                       'image/gif': '.gif'} if kind == 'image' else {'video/mp4': '.mp4', 'application/octet-stream': '.mp4'}
            suffix = allowed.get(content_type)
            if not suffix:
                raise RuntimeError('媒体地址返回了不支持的内容类型')
            output = target.with_suffix(suffix)
            count = 0
            with output.open('xb') as file:
                for chunk in response.iter_content(256 * 1024):
                    file.write(chunk)
                    count += len(chunk)
            length = response.headers.get('Content-Length')
            if not count or (length and not response.headers.get('Content-Encoding') and count != int(length)):
                raise RuntimeError('小红书媒体未完整下载')
            return output


def download(url, outdir, env, *, audio=False, meta_only=False, cookies=None):
    note = None
    try:
        note = tikhub_note(url, env)
    except (requests.RequestException, ValueError, RuntimeError):
        pass  # Public-page parsing is an independent, established fallback.
    if not note:
        _, note, _ = xhs_resolve_and_fetch(url, cookies)
    if not note:
        raise RuntimeError('未解析到小红书笔记；保留完整分享参数，检查 TikHub 权限或本机登录 Cookie')
    meta = {'title': note.get('title', ''), 'uploader': (note.get('user') or {}).get('nickname', '')}
    if meta_only:
        return {'meta': meta, 'files': []}
    outdir.mkdir(parents=True, exist_ok=True)
    prefix = 'XHS-' + (re.sub(r'[^\w-]', '-', note.get('title') or 'note')[:60].strip('-') or 'note')
    files = []
    if note.get('type') == 'video':
        _, urls = _xhs_pick_video_stream(note)
        if not urls:
            raise RuntimeError('笔记没有可下载视频')
        video = fetch_asset(urls[0], outdir / prefix, env, 'video')
        if audio:
            ffmpeg = ffmpeg_path(env)
            if not ffmpeg:
                raise RuntimeError('提取音频需要 FFmpeg')
            mp3 = video.with_suffix('.mp3')
            converted = subprocess.run([ffmpeg, '-nostdin', '-n', '-i', str(video), '-vn', '-c:a', 'libmp3lame', str(mp3)],
                                       capture_output=True, timeout=1800)
            if converted.returncode or not mp3.is_file():
                raise RuntimeError('小红书视频无法提取音频，可能没有音轨')
            files.append(mp3)
        else:
            files.append(video)
    else:
        if audio:
            raise RuntimeError('小红书图文笔记没有视频音轨')
        images = note.get('imageList') or []
        for index, item in enumerate(images, 1):
            image = _xhs_best_image_url(item)
            if not image:
                raise RuntimeError('笔记有图片未返回下载地址')
            files.append(fetch_asset(image, outdir / f'{prefix}-{index:02d}', env, 'image'))
    if not audio:
        text = outdir / f'{prefix}.txt'
        text.write_text(f"{note.get('title', '')}\n\n{note.get('desc', '')}\n\n原帖：{url}\n", encoding='utf-8')
        files.append(text)
    return {'meta': meta, 'files': files}

def xhs_resolve_and_fetch(url: str, user_cookies: str | None):
    """跟随短链 → 抓 explore 页 → 解析 window.__INITIAL_STATE__. 返回 (final_url, note_dict|None, html)."""
    import requests
    headers = {"User-Agent": UA, "Referer": "https://www.xiaohongshu.com/"}
    cookie_str = ""
    if user_cookies and Path(user_cookies).exists():
        # Netscape cookiejar → Cookie 头
        jar = MozillaCookieJar(user_cookies)
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
            cookie_str = "; ".join(f"{c.name}={c.value}" for c in jar)
        except Exception:
            pass
    if cookie_str:
        headers["Cookie"] = cookie_str
    sess = requests.Session(); sess.trust_env = False   # 国内站直连
    r = sess.get(url, headers=headers, timeout=20, allow_redirects=True)
    html = r.text
    note = None
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})</script>", html, re.S)
    if m:
        raw = m.group(1).replace("undefined", "null")
        try:
            state = json.loads(raw)
            note = _xhs_pick_note(state)
        except Exception:
            note = None
    return r.url, note, html

def _xhs_pick_note(state: dict):
    """从 __INITIAL_STATE__ 里挖出当前笔记 dict (结构随版本变, 尽量鲁棒)。"""
    nd = (state.get("note") or {})
    detail = nd.get("noteDetailMap") or nd.get("note") or {}
    if isinstance(detail, dict) and detail:
        # noteDetailMap: {noteId: {note: {...}}}
        for v in detail.values():
            if isinstance(v, dict) and v.get("note"):
                return v["note"]
        if detail.get("title") or detail.get("imageList"):
            return detail
    return None

def _xhs_best_image_url(im: dict) -> str | None:
    """从一个 imageList 元素里挑最高清的无水印图 URL。
    infoList 里 WB_DFT 通常是默认展示图; 优先它, 回退 urlDefault。"""
    candidates = []
    for it in (im.get("infoList") or []):
        if it.get("url"):
            candidates.append((it.get("imageScene") or "", it["url"]))
    for scene in ("WB_DFT", "WB_PRV"):
        for sc, u in candidates:
            if sc == scene:
                return u
    return im.get("urlDefault") or im.get("url") or (candidates[0][1] if candidates else None)

def _xhs_pick_video_stream(note: dict):
    """从 note.video.media.stream 里挑最高清的视频流。优先 h264(最通用)。返回 (stream_item, [urls])。"""
    stream = (((note.get("video") or {}).get("media") or {}).get("stream") or {})
    for codec in ("h264", "h265", "av1", "h266"):
        arr = stream.get(codec) or []
        if arr:
            best = max(arr, key=lambda s: ((s.get("width") or 0) * (s.get("height") or 0),
                                           s.get("videoBitrate") or 0))
            urls = [u for u in ([best.get("masterUrl")] + (best.get("backupUrls") or [])) if u]
            if urls:
                return best, urls
    return None, []
