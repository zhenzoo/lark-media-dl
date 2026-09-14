import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from media_dl import cli
from media_dl.config import load_config
from media_dl.downloader import download, detect_platform
from media_dl.platforms.threads import ThreadsClient, find_post, media_assets
from media_dl.delivery import deliver
from media_dl.worker import Worker

URL = 'https://www.threads.com/@owner/post/DZ-qt1UEkbX'
POST = {'code': 'DZ-qt1UEkbX', 'media_type': 19, 'caption': {'text': '正文'}, 'user': {'username': 'owner'}}
ENV = {'TIKHUB_API_KEY': 'test-key'}


class DownloadTests(unittest.TestCase):
    def test_host_validation_and_platforms(self):
        for url, name in [('https://youtu.be/id', 'youtube'), ('https://b23.tv/id', 'bilibili'),
                          ('https://xhslink.com/id', 'xiaohongshu'), ('https://x.com/u/status/1', 'x'), (URL, 'threads')]:
            self.assertEqual(detect_platform(url), name)
        for url in ['https://youtube.com.evil.test/a', 'http://youtube.com/a', 'https://user@x.com/a', 'https://localhost/a']:
            with self.assertRaises(ValueError):
                detect_platform(url)

    def test_text_defaults_and_collision(self):
        with tempfile.TemporaryDirectory() as tmp, patch('media_dl.downloader.Path.home', return_value=Path(tmp)), \
             patch.object(ThreadsClient, 'fetch_post', return_value=POST):
            first = download(URL, ENV)
            second = download(URL, ENV)
            a, b = Path(first['files'][0]), Path(second['files'][0])
            self.assertEqual(a.parent, Path(tmp) / 'Downloads')
            self.assertNotEqual(a, b)
            self.assertEqual(a.read_text(encoding='utf-8'), b.read_text(encoding='utf-8'))
            self.assertIn('正文', a.read_text(encoding='utf-8'))

    def test_metadata_no_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ThreadsClient, 'fetch_post', return_value=POST):
            target = Path(tmp) / 'absent'
            result = download(URL, ENV, outdir=target, meta_only=True)
            self.assertEqual(result['meta']['uploader'], 'owner')
            self.assertFalse(target.exists())

    def test_carousel_order_and_no_cover_substitution(self):
        post = {'carousel_media': [{'image_versions2': {'candidates': [{'url': 'image'}]}},
                                  {'video_versions': [{'url': 'video'}], 'image_versions2': {'candidates': [{'url': 'cover'}]}}]}
        self.assertEqual([a.url for a in media_assets(post, '1080')], ['image', 'video'])
        with self.assertRaises(RuntimeError):
            media_assets({'media_type': 2}, 'best')

    def test_exact_post(self):
        self.assertIs(find_post({'posts': [{'code': 'other'}, POST]}, POST['code']), POST)
        with self.assertRaises(RuntimeError):
            find_post({'posts': [POST]}, 'missing')

    def test_failure_does_not_publish_files(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ThreadsClient, 'fetch_post', return_value=POST), \
             patch.object(ThreadsClient, 'download', side_effect=RuntimeError('interrupted')):
            target = Path(tmp) / 'out'
            with self.assertRaises(RuntimeError):
                download(URL, ENV, outdir=target)
            self.assertFalse(target.exists())

    def test_missing_key_json_and_no_audio(self):
        output = io.StringIO()
        with patch('media_dl.cli.load_config', return_value={}), contextlib.redirect_stdout(output):
            self.assertEqual(cli.main([URL, '--json']), 1)
        self.assertFalse(json.loads(output.getvalue())['ok'])
        with patch.object(ThreadsClient, 'fetch_post', return_value=POST), self.assertRaises(RuntimeError):
            download(URL, ENV, audio=True)

    def test_configuration_process_wins_and_no_private_paths(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'TIKHUB_API_KEY': 'process-key', 'USERPROFILE': tmp, 'HOME': tmp}, clear=True):
            path = Path(tmp) / '.env'
            path.write_text('TIKHUB_API_KEY="file-key"\nMEDIA_DELIVERY=local\n', encoding='utf-8')
            self.assertEqual(load_config(str(path))['TIKHUB_API_KEY'], 'process-key')

    def test_youtube_and_bilibili_use_shared_download_contract(self):
        def fake(url, platform, outdir, *args, **kwargs):
            p = outdir / (platform + '.mp4')
            p.write_bytes(b'finished-media')
            return {'files': [p]}
        with tempfile.TemporaryDirectory() as tmp, patch('media_dl.platforms.ytdlp.download', side_effect=fake):
            for url in ('https://youtu.be/id', 'https://b23.tv/id'):
                result = download(url, {}, outdir=tmp)
                self.assertTrue(Path(result['files'][0]).is_file())

    def test_local_delivery_has_no_cloud_dependency(self):
        self.assertEqual(deliver(['/any/result.txt'], 'job', {}), {'outputName': 'result.txt'})


class WorkerTests(unittest.TestCase):
    def worker(self):
        return Worker({'MEDIA_WORKER_API_BASE': 'http://localhost:9123', 'MEDIA_WORKER_API_KEY': 'test-worker-key', 'MEDIA_WORKER_ID': 'test'})

    def job(self):
        return {'id': 'job-1', 'platform': 'threads', 'sourceUrl': URL, 'workflow': 'video', 'quality': '1080'}

    def test_local_completed_without_delivery_url(self):
        worker = self.worker()
        worker.update = Mock()
        worker.wait_for = Mock(return_value={'files': ['/tmp/result.txt'], 'meta': {'title': 'text'}})
        self.assertTrue(worker.process(self.job()))
        result = worker.update.call_args.kwargs
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['outputName'], 'result.txt')
        self.assertNotIn('deliveryUrl', result)

    def test_mismatched_platform_rejected_before_download(self):
        worker = self.worker()
        worker.update = Mock()
        worker.wait_for = Mock()
        job = self.job()
        job['platform'] = 'youtube'
        self.assertFalse(worker.process(job))
        worker.wait_for.assert_not_called()

    def test_failed_download_reports_error_and_never_completed(self):
        worker = self.worker()
        worker.update = Mock()
        worker.wait_for = Mock(side_effect=RuntimeError('network failed'))
        self.assertFalse(worker.process(self.job()))
        self.assertEqual(worker.update.call_args.kwargs['status'], 'failed')

    def test_fake_localhost_rejected(self):
        with self.assertRaises(ValueError):
            Worker({'MEDIA_WORKER_API_BASE': 'http://localhost.evil.test', 'MEDIA_WORKER_API_KEY': 'key'})

    def test_worker_api_never_follows_redirect_with_key(self):
        worker = self.worker()
        worker.session.request = Mock(return_value=Mock(status_code=302))
        with self.assertRaises(RuntimeError):
            worker.request('GET', '/next')
        self.assertFalse(worker.session.request.call_args.kwargs['allow_redirects'])


if __name__ == '__main__':
    unittest.main()
