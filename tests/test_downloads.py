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
from media_dl.platforms import linkedin, x
from media_dl.delivery import deliver
from media_dl.worker import Worker

URL = 'https://www.threads.com/@owner/post/DZ-qt1UEkbX'
POST = {'code': 'DZ-qt1UEkbX', 'media_type': 19, 'caption': {'text': '正文'}, 'user': {'username': 'owner'}}
ENV = {'TIKHUB_API_KEY': 'test-key'}


class DownloadTests(unittest.TestCase):
    def test_host_validation_and_platforms(self):
        for url, name in [('https://youtu.be/id', 'youtube'), ('https://b23.tv/id', 'bilibili'),
                          ('https://xhslink.com/id', 'xiaohongshu'), ('https://x.com/u/status/1', 'x'), (URL, 'threads'),
                          ('https://www.linkedin.com/posts/u_slug-activity-7505337342660939776-Az3R', 'linkedin'),
                          ('https://lnkd.in/abc', 'linkedin')]:
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
            # macOS /var symlinks and Windows 8.3 names may spell the same directory differently.
            self.assertTrue(a.parent.samefile(Path(tmp) / 'Downloads'))
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

    def test_linkedin_page_parser_keeps_only_the_main_post(self):
        page = (
            '<meta property="og:image" content="https://media.licdn.com/dms/image/v2/MAIN/feedshare-shrink_800/a?e=1&amp;t=og">'
            '<article class="main-feed-activity-card main-feed-activity">'
            '<a data-tracking-control-name="public_post_feed-actor-name"> Owner </a>'
            '<p class="attributed-text-segment-list__content" data-test-id="main-feed-activity-card__commentary">Body &amp; more<br/>two</p>'
            '<p class="attributed-text-segment-list__content comment__text">a comment</p>'
            '<ul data-test-id="feed-images-content"><li><img data-delayed-url="https://media.licdn.com/dms/image/v2/MAIN/feedshare-shrink_800/a?e=1&amp;t=x"></li>'
            '<li><img data-delayed-url="https://static.licdn.com/icon"></li></ul></article>'
            '<article class="main-feed-activity-card related-posts__cro"><video></video>'
            '<ul data-test-id="feed-images-content"><li><img data-delayed-url="https://media.licdn.com/dms/image/v2/OTHER/feedshare-shrink_800/b"></li></ul></article>')
        post = linkedin.parse_page(page)
        self.assertEqual(post['author'], 'Owner')
        self.assertEqual(post['text'], 'Body & more\ntwo')
        self.assertEqual(post['images'], ['https://media.licdn.com/dms/image/v2/MAIN/feedshare-shrink_800/a?e=1&t=x'])
        self.assertFalse(post['has_video'])
        self.assertIsNone(linkedin.parse_page('<article class="related-posts__cro"></article>'))

    def test_linkedin_text_and_images_without_any_key(self):
        post = {'text': 'Hello', 'author': 'Owner', 'images': ['https://media.licdn.com/dms/image/v2/MAIN/feedshare-shrink_800/a'], 'has_video': False}
        def fake_image(url, proxy, target):
            path = target.with_suffix('.jpg'); path.write_bytes(b'jpg'); return path
        with tempfile.TemporaryDirectory() as tmp, patch.object(linkedin, 'fetch_page', return_value=post), \
             patch.object(linkedin, 'fetch_image', side_effect=fake_image):
            result = download('https://www.linkedin.com/posts/u_slug-activity-7505337342660939776-Az3R', {}, outdir=tmp)
            names = sorted(Path(f).name for f in result['files'])
            self.assertEqual(names, ['linkedin-7505337342660939776-01.jpg', 'linkedin-7505337342660939776.txt'])
            self.assertIn('Hello', (Path(tmp) / 'linkedin-7505337342660939776.txt').read_text(encoding='utf-8'))
            self.assertEqual(result['meta']['uploader'], 'Owner')
            meta = download('https://www.linkedin.com/posts/u_slug-activity-7505337342660939776-Az3R', {}, outdir=tmp, meta_only=True)
            self.assertEqual(meta['meta']['title'], 'Hello')
            with self.assertRaises(RuntimeError):   # no video -> no audio, and nothing is published
                download('https://www.linkedin.com/posts/u_slug-activity-7505337342660939776-Az3R', {}, outdir=tmp, audio=True)

    def test_linkedin_video_uses_shared_ytdlp_contract(self):
        post = {'text': '', 'author': 'Owner', 'images': [], 'has_video': True}
        def fake_yt(url, platform, outdir, env, **kwargs):
            self.assertEqual((platform, kwargs['quality'], kwargs['audio']), ('linkedin', 'best', False))
            p = outdir / 'clip-1.mp4'; p.write_bytes(b'finished-media'); return {'files': [p]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(linkedin, 'fetch_page', return_value=post), \
             patch('media_dl.platforms.ytdlp.download', side_effect=fake_yt):
            result = download('https://www.linkedin.com/posts/u_slug-ugcPost-7503022951252828161-eXh5?utm=1', {}, outdir=tmp)
            self.assertEqual([Path(f).name for f in result['files']], ['clip-1.mp4'])

    def test_x_saves_every_video_photo_and_text_in_order(self):
        tweet = {'id': '2100912907038896466', 'author': 'LN_Data', 'text': 'two clips', 'title': 'two clips',
                 'media': [{'type': 'video', 'm3u8': 'https://v/1.m3u8', 'direct_url': 'https://v/1.mp4', 'duration': 7.2},
                           {'type': 'photo', 'url': 'https://pbs.twimg.com/media/a.jpg?name=orig'},
                           {'type': 'video', 'm3u8': None, 'direct_url': 'https://v/2.mp4', 'duration': 9.2}]}
        calls = []
        def fake_yt(url, platform, outdir, env, **kwargs):
            calls.append((url, kwargs['name']))
            p = outdir / (kwargs['name'] + '.mp4'); p.write_bytes(b'finished-media'); return {'files': [p]}
        def fake_photo(url, stem, proxy):
            p = stem.with_suffix('.jpg'); p.write_bytes(b'jpg'); return p
        with tempfile.TemporaryDirectory() as tmp, patch.object(x, 'twitter_via_fxtwitter', return_value=tweet), \
             patch('media_dl.platforms.ytdlp.download', side_effect=fake_yt), patch.object(x, 'fetch_photo', side_effect=fake_photo):
            result = download('https://x.com/LN_Data/status/2100912907038896466?s=20', {}, outdir=tmp)
            self.assertEqual(sorted(Path(f).name for f in result['files']),
                             ['x-2100912907038896466-01.jpg', 'x-2100912907038896466-01.mp4',
                              'x-2100912907038896466-02.mp4', 'x-2100912907038896466.txt'])
            self.assertEqual(calls, [('https://v/1.m3u8', 'x-2100912907038896466-01'), ('https://v/2.mp4', 'x-2100912907038896466-02')])
            self.assertEqual((result['meta']['video_count'], result['meta']['photo_count']), (2, 1))
            meta = download('https://x.com/LN_Data/status/2100912907038896466', {}, outdir=tmp, meta_only=True)
            self.assertEqual(meta['meta']['uploader'], 'LN_Data')

    def test_x_media_items_keep_order_and_prefer_m3u8(self):
        tw = {'media': {'all': [{'type': 'photo', 'url': 'https://pbs.twimg.com/media/a.jpg'},
                                {'type': 'video', 'url': 'https://v/best.mp4', 'formats': [{'container': 'mp4', 'url': 'https://v/low.mp4'}, {'container': 'm3u8', 'url': 'https://v/pl.m3u8'}]}]}}
        items = x.media_items(tw)
        self.assertEqual([i['type'] for i in items], ['photo', 'video'])
        self.assertEqual(items[0]['url'], 'https://pbs.twimg.com/media/a.jpg?name=orig')
        self.assertEqual((items[1]['m3u8'], items[1]['direct_url']), ('https://v/pl.m3u8', 'https://v/best.mp4'))
        with tempfile.TemporaryDirectory() as tmp, patch.object(x, 'twitter_via_fxtwitter', return_value={'id': '1', 'author': 'a', 'text': 't', 'title': 't', 'media': []}):
            with self.assertRaises(RuntimeError):   # no video -> audio mode fails closed
                download('https://x.com/a/status/1', {}, outdir=tmp, audio=True)

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
