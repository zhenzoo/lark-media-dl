"""Optional queue consumer. Downloads run without an agent or LLM session."""
import argparse
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import re
import signal
import tempfile
import time
from contextlib import contextmanager
from urllib.parse import urlparse
import requests
from . import __version__
from .config import load_config, config_dir, redact
from .downloader import download, detect_platform
from .delivery import deliver, validate as validate_delivery

LOGGER = logging.getLogger('media-dl-worker')


@contextmanager
def single_instance(base, worker_id):
    digest = hashlib.sha256((base + '\0' + worker_id).encode()).hexdigest()[:16]
    path = Path(tempfile.gettempdir()) / f'lark-media-dl-worker-{digest}.lock'
    with path.open('a+b') as lock:
        if path.stat().st_size == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError('同一电脑标识的 Worker 已在运行') from error
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


class Worker:
    def __init__(self, env):
        self.env = env
        self.base = env.get('MEDIA_WORKER_API_BASE', '').rstrip('/')
        parsed = urlparse(self.base)
        if (parsed.username or parsed.password or parsed.query or parsed.fragment or
                not (parsed.scheme == 'https' and parsed.hostname or
                     parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1'))):
            raise ValueError('Worker API 必须是 HTTPS 或准确的 localhost 开发地址')
        self.key = env.get('MEDIA_WORKER_API_KEY', '')
        self.worker_id = env.get('MEDIA_WORKER_ID') or re.sub('[^A-Za-z0-9._-]', '-', platform.node())[:128]
        if not self.key or not re.fullmatch(r'[A-Za-z0-9._-]{1,128}', self.worker_id):
            raise ValueError('请配置 MEDIA_WORKER_API_KEY 和有效的 MEDIA_WORKER_ID')
        validate_delivery(env)
        self.stop = False
        self.session = requests.Session()
        self.session.trust_env = False
        self.state = config_dir() / 'worker-status.json'

    def request(self, method, path, body=None):
        response = self.session.request(method, self.base + path, json=body,
            headers={'Authorization': 'Bearer ' + self.key, 'Accept': 'application/json'}, timeout=(10, 30), allow_redirects=False)
        if response.status_code != 200 and response.status_code != 201:
            raise RuntimeError(f'任务接口 HTTP {response.status_code}；检查应用地址及 Worker Key')
        result = response.json()
        if result.get('code') not in (None, 0, '0'):
            raise RuntimeError('任务接口拒绝请求；检查后台日志')
        return result.get('data', result)

    def heartbeat(self):
        self.request('POST', '/openapi/jobs/worker/heartbeat', {'workerId': self.worker_id, 'version': __version__})
        self.state.parent.mkdir(parents=True, exist_ok=True)
        self.state.write_text(json.dumps({'worker_id': self.worker_id, 'pid': os.getpid(),
            'last_seen': time.time(), 'delivery': self.env.get('MEDIA_DELIVERY', 'local')}), encoding='utf-8')

    def update(self, job, **fields):
        return self.request('POST', '/openapi/jobs/update', {'jobId': job['id'], 'workerId': self.worker_id, **fields})

    def wait_for(self, work, job, status, progress):
        # Refresh the job lease as well as the machine heartbeat during long downloads/uploads.
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(work)
            while True:
                try:
                    return future.result(timeout=15)
                except TimeoutError:
                    self.heartbeat()
                    self.update(job, status=status, progress=progress)

    def process(self, job):
        try:
            if not re.fullmatch(r'[A-Za-z0-9-]{1,80}', str(job.get('id', ''))):
                raise ValueError('无效任务标识')
            workflow = job.get('workflow')
            if workflow not in ('video', 'audio', 'inspect') or job.get('quality') not in ('best', '1080', '720', '480'):
                raise ValueError('未知任务类型或画质')
            if detect_platform(job['sourceUrl']) != job.get('platform'):
                raise ValueError('任务链接与平台不匹配')
            status = 'inspecting' if workflow == 'inspect' else 'downloading'
            self.update(job, status=status, progress=15)
            result = self.wait_for(lambda: download(job['sourceUrl'], self.env,
                audio=workflow == 'audio', meta_only=workflow == 'inspect', quality=job['quality']), job, status, 35)
            meta = result.get('meta') or {}
            fields = {k: str(meta[k])[:1000 if k == 'title' else 255] for k in ('title', 'uploader') if meta.get(k)}
            if workflow != 'inspect':
                if self.env.get('MEDIA_DELIVERY', 'local') == 'oss':
                    self.update(job, status='uploading', progress=85, **fields)
                    fields.update(self.wait_for(lambda: deliver(result['files'], job['id'], self.env), job, 'uploading', 85))
                else:
                    fields.update(deliver(result['files'], job['id'], self.env))
            self.update(job, status='completed', progress=100, **fields)
            LOGGER.info('任务 %s 完成，交付模式 %s', job['id'], self.env.get('MEDIA_DELIVERY', 'local'))
            return True
        except Exception as error:
            message = redact(str(error), self.env)
            LOGGER.error('任务 %s 失败：%s', job.get('id'), message)
            try:
                self.update(job, status='failed', errorMessage=message)
            except Exception:
                LOGGER.error('失败状态回传未成功；租约到期后云端会重新排队')
            return False

    def run(self, once=False):
        with single_instance(self.base, self.worker_id):
            while not self.stop:
                try:
                    self.heartbeat()
                    payload = self.request('GET', '/openapi/jobs/next?workerId=' + self.worker_id)
                    if payload.get('job'):
                        ok = self.process(payload['job'])
                        if once:
                            return 0 if ok else 1
                    elif once:
                        return 0
                    deadline = time.monotonic() + min(15, max(2, payload.get('pollAfterSeconds', 4)))
                    while not self.stop and time.monotonic() < deadline:
                        time.sleep(0.5)
                except Exception as error:
                    LOGGER.error('%s', redact(str(error), self.env))
                    if once:
                        return 1
                    time.sleep(5)
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--log-file', type=Path)
    args = parser.parse_args(argv)
    handlers = []
    if args.log_file:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(args.log_file, maxBytes=2_000_000, backupCount=3, encoding='utf-8'))
    else:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers, format='%(asctime)s %(levelname)s %(message)s')
    env = {}
    try:
        env = load_config(args.env_file)
        worker = Worker(env)
        if args.check:
            print(json.dumps({'ok': True, 'worker_id': worker.worker_id, 'api_host': urlparse(worker.base).hostname,
                              'api_key': 'configured', 'delivery': env.get('MEDIA_DELIVERY', 'local')}))
            return 0
        def stop(*_):
            worker.stop = True
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        return worker.run(args.once)
    except Exception as error:
        LOGGER.error('%s', redact(str(error), env))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
