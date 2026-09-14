"""Command-line download entry."""
import argparse
import json
from .config import load_config, redact
from .downloader import download


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='媒体保存到电脑 Downloads；无需 OSS 或飞书')
    parser.add_argument('url')
    parser.add_argument('-o', '--outdir')
    parser.add_argument('--audio', action='store_true')
    parser.add_argument('--meta-only', action='store_true')
    parser.add_argument('--quality', default='1080')
    parser.add_argument('--cookies')
    parser.add_argument('--cookies-from-browser')
    parser.add_argument('--proxy', help='媒体代理地址；空字符串表示直连')
    parser.add_argument('--env-file')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    env = {}
    try:
        env = load_config(args.env_file)
        if args.proxy is not None:
            env['MEDIA_DL_PROXY'] = args.proxy
            env.pop('HTTPS_PROXY', None)
        result = download(args.url, env, outdir=args.outdir, audio=args.audio,
                          meta_only=args.meta_only, quality=args.quality, cookies=args.cookies,
                          browser=args.cookies_from_browser)
    except Exception as error:
        result = {'ok': False, 'error': redact(str(error), env),
                  'hint': '运行 media-dl-doctor；按实际错误检查网络、平台权限、Key 余额或登录状态。'}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result['ok']:
        print('完成：' + result['platform'])
        if args.meta_only:
            print(json.dumps(result['meta'], ensure_ascii=False, indent=2))
        for file in result.get('files', []):
            print(file)
    else:
        print(result['error'])
        print(result['hint'])
    return 0 if result['ok'] else 1
