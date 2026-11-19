"""Resolve a public WeChat Channels share link and save the playable media."""
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import HTTPError as StreamError
from urllib3.util.retry import Retry

from ..media_output import require_ffmpeg


API_PATH = '/api/v1/wechat_channels/v2/fetch_video_detail'
HEADER_BYTES = 131072


def fetch_detail(share_url, env):
    key = env.get('TIKHUB_API_KEY', '').strip()
    if not key:
        raise ValueError('微信视频号需要有视频号详情权限及余额的 TIKHUB_API_KEY')
    base = env.get('TIKHUB_BASE') or 'https://api.tikhub.io'
    if urlsplit(base).scheme != 'https':
        raise ValueError('TIKHUB_BASE 必须是 HTTPS 地址')
    with requests.Session() as api:
        api.trust_env = False
        # TLS negotiation can end early. Never retry a read timeout on the billed POST.
        api.mount('https://', HTTPAdapter(max_retries=Retry(total=2, connect=2, read=0, other=2,
                                                            backoff_factor=0.5)))
        try:
            response = api.post(base.rstrip('/') + API_PATH, json={'share_url': share_url, 'raw': False},
                                headers={'Authorization': 'Bearer ' + key, 'Accept-Encoding': 'identity'},
                                allow_redirects=False, timeout=(15, 65))
        except requests.RequestException:
            raise RuntimeError('TikHub 视频号接口连接失败，请检查网络与 TIKHUB_BASE') from None
        if response.status_code != 200:
            raise RuntimeError(f'TikHub 视频号详情返回 HTTP {response.status_code}，请检查余额、权限或服务状态')
        payload = response.json()
    if payload.get('code') != 200 or not isinstance(payload.get('data'), dict):
        raise RuntimeError('TikHub 未返回这条视频号作品的详情')
    return payload['data']


def fetch_video(media, path, env):
    url = urlsplit(media.get('full_url') or '')
    host = url.hostname or ''
    if (url.scheme not in ('http', 'https') or url.username or url.password or url.port not in (None, 443)
            or not any(host == d or host.endswith('.' + d) for d in ('qq.com', 'qpic.cn'))):
        raise RuntimeError('视频号详情缺少受支持的腾讯媒体地址')
    cdn_url = urlunsplit(url._replace(scheme='https'))
    with requests.Session() as cdn:
        cdn.trust_env = False
        proxy = env.get('MEDIA_DL_PROXY', env.get('HTTPS_PROXY'))
        if proxy:
            cdn.proxies.update(http=proxy, https=proxy)
        for attempt in range(3):
            try:
                with cdn.get(cdn_url, headers={'Accept-Encoding': 'identity'}, stream=True,
                             allow_redirects=False, timeout=(15, 90)) as response:
                    if response.status_code != 200:
                        raise RuntimeError(f'视频号媒体返回 HTTP {response.status_code}，请重新解析分享链接')
                    prefix = response.raw.read(HEADER_BYTES, decode_content=True)
                    if prefix[4:8] != b'ftyp' and media.get('decode_key') is not None:
                        from wxipad_video import decrypt_data
                        prefix = decrypt_data(prefix, int(media['decode_key']))
                    if prefix[4:8] != b'ftyp':
                        raise RuntimeError('视频号媒体未还原为 MP4')
                    with path.open('wb') as output:
                        output.write(prefix)
                        for chunk in response.iter_content(1024 * 1024):
                            output.write(chunk)
                return
            except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError, StreamError):
                if attempt == 2:
                    raise RuntimeError('视频号媒体传输中断，已用同一次解析的地址重试') from None
                time.sleep(attempt + 1)


def download(url: str, scratch: Path, env: dict, *, audio=False, meta_only=False):
    share_id = re.fullmatch(r'/sph/([A-Za-z0-9]+)/?', urlsplit(url).path)
    if not share_id:
        raise ValueError('请粘贴 https://weixin.qq.com/sph/ 开头的视频号分享链接')
    detail = fetch_detail('https://weixin.qq.com/sph/' + share_id[1], env)
    media = detail.get('media') or {}
    meta = {'title': detail.get('title') or detail.get('description'), 'uploader': detail.get('nickname'),
            'id': str(detail.get('id') or share_id[1]), 'duration': media.get('duration')}
    if meta_only:
        return {'meta': meta, 'files': []}
    ffmpeg = require_ffmpeg(env)
    video = scratch / ('wechat-' + share_id[1] + '.mp4')
    fetch_video(media, video, env)
    command = [ffmpeg, '-nostdin', '-v', 'error', '-xerror', '-i', str(video)]
    if audio:
        target = video.with_suffix('.mp3')
        command += ['-map', '0:a:0', '-vn', '-c:a', 'libmp3lame', '-q:a', '2', str(target)]
    else:
        target = video
        command += ['-map', '0:v:0', '-map', '0:a?', '-f', 'null', '-']
    if subprocess.run(command, capture_output=True).returncode or not target.stat().st_size:
        raise RuntimeError('微信视频号 MP3 提取失败，请确认原片有可解码音轨' if audio else '微信视频号 MP4 完整解码失败')
    return {'meta': meta, 'files': [target]}
