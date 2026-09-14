"""Inspect dependencies and connectivity without exposing credentials."""
import argparse
import importlib.metadata
import json
import shutil
import sys
from urllib.parse import urlparse
from .config import load_config, ffmpeg_path, config_dir, redact


def inspect(env, platform=None, network=False):
    rows = []
    def add(name, ok, detail, required=True):
        rows.append(dict(name=name, ok=bool(ok), required=required, detail=detail))
    add('python', sys.version_info >= (3, 10), sys.version.split()[0])
    for name in ('requests', 'yt-dlp'):
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            version = None
        add(name, version, version or 'missing', name == 'requests' or platform in (None, 'youtube', 'bilibili', 'x'))
    ffmpeg = ffmpeg_path(env)
    add('ffmpeg', ffmpeg, 'available' if ffmpeg else 'missing; install FFmpeg or imageio-ffmpeg')
    js = env.get('MEDIA_DL_JS_RUNTIME') or next((x for x in ('deno', 'node', 'bun', 'qjs') if shutil.which(x)), None)
    add('youtube-js', js, (js + '; verify version with yt-dlp docs') if js else 'missing', platform == 'youtube')
    key = env.get('TIKHUB_API_KEY', '').strip()
    add('tikhub-key', key, 'configured; permission and balance require a real request' if key else 'missing', platform == 'threads')
    add('proxy', True, 'configured' if env.get('MEDIA_DL_PROXY') or env.get('HTTPS_PROXY') else 'direct connection', False)
    add('cookies', True, 'configured' if any(k.endswith('_COOKIES') and v for k, v in env.items()) else 'not configured; optional for public content', False)
    add('config-location', True, str(config_dir() / '.env'), False)
    if network:
        import requests
        urls = {'youtube': 'https://www.youtube.com', 'bilibili': 'https://www.bilibili.com',
                'x': 'https://api.fxtwitter.com', 'xiaohongshu': 'https://www.xiaohongshu.com',
                'threads': env.get('TIKHUB_BASE', 'https://api.tikhub.dev')}
        for name, url in urls.items():
            if platform and name != platform:
                continue
            try:
                with requests.Session() as session:
                    session.trust_env = False
                    proxy = env.get('MEDIA_DL_PROXY') or env.get('HTTPS_PROXY')
                    if proxy and name != 'threads':
                        session.proxies.update(http=proxy, https=proxy)
                    response = session.get(url, timeout=(5, 10), stream=True)
                    code = response.status_code
                    response.close()
                add('network-' + name, True, f'HTTP {code}; connectivity only, not download authorization')
            except requests.RequestException:
                add('network-' + name, False, 'connection failed; inspect DNS, proxy and network')
    return {'ok': all(row['ok'] for row in rows if row['required']), 'checks': rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=['youtube', 'bilibili', 'x', 'xiaohongshu', 'threads'])
    parser.add_argument('--env-file')
    parser.add_argument('--network', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = inspect(load_config(args.env_file), args.platform, args.network)
    except Exception as error:
        result = {'ok': False, 'error': str(error), 'checks': []}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for row in result['checks']:
            mark = 'OK' if row['ok'] else ('MISSING' if row['required'] else 'OPTIONAL')
            print(f"{mark:8} {row['name']}: {row['detail']}")
        if result.get('error'):
            print(result['error'])
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
