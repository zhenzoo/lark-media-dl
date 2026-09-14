"""Optional delivery after local download. The default never uploads files."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import tempfile
import zipfile
from urllib.parse import urlparse


def validate(env):
    mode = env.get('MEDIA_DELIVERY', 'local')
    if mode not in ('local', 'oss'):
        raise ValueError('MEDIA_DELIVERY 目前只支持 local 或 oss；妙搭存储尚未接入')
    if mode == 'oss':
        for name in ('OSS_BUCKET', 'OSS_ENDPOINT', 'OSS_REGION', 'OSS_ACCESS_KEY_ID', 'OSS_ACCESS_KEY_SECRET'):
            if not env.get(name):
                raise ValueError('OSS 交付缺少配置：' + name)
        endpoint = urlparse(env['OSS_ENDPOINT'])
        if endpoint.scheme != 'https' or endpoint.username or endpoint.password:
            raise ValueError('OSS_ENDPOINT 必须是 HTTPS 地址')
        if not 1 <= int(env.get('OSS_URL_DAYS', '1')) <= 7:
            raise ValueError('OSS_URL_DAYS 请设为 1 到 7 天')
        try:
            import oss2
        except ImportError as error:
            raise RuntimeError('请安装可选依赖：pip install "lark-media-dl[oss]" 或从仓库安装 ".[oss]"') from error


def deliver(files: list[str], job_id: str, env: dict) -> dict:
    validate(env)
    if env.get('MEDIA_DELIVERY', 'local') == 'local':
        names = '; '.join(Path(p).name for p in files)
        if len(names) > 1000:
            names = f'{Path(files[0]).name[:900]} … ({len(files)} files)'
        return {'outputName': names}
    import oss2
    auth = oss2.AuthV4(env['OSS_ACCESS_KEY_ID'], env['OSS_ACCESS_KEY_SECRET'])
    bucket = oss2.Bucket(auth, env['OSS_ENDPOINT'], env['OSS_BUCKET'], region=env['OSS_REGION'])
    with tempfile.TemporaryDirectory(prefix='lark-media-delivery-') as tmp:
        if len(files) == 1:
            artifact = Path(files[0])
        else:
            artifact = Path(tmp) / f'media-{job_id}.zip'
            with zipfile.ZipFile(artifact, 'w', zipfile.ZIP_DEFLATED) as archive:
                for file in files:
                    archive.write(file, arcname=Path(file).name)
        key = f'lark-media-dl/{job_id}/{artifact.name}'
        # Upload private objects. Bucket lifecycle configuration owns eventual deletion.
        oss2.resumable_upload(bucket, key, str(artifact), headers={'x-oss-object-acl': 'private'})
        seconds = int(env.get('OSS_URL_DAYS', '1')) * 86400
        url = bucket.sign_url('GET', key, seconds, slash_safe=True)
    return {'outputName': artifact.name, 'deliveryUrl': url,
            'deliveryExpiresAt': (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()}
