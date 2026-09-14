import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from media_dl.media_output import final_media, require_ffmpeg


class FinalMediaTests(unittest.TestCase):
    def test_missing_merger_record_never_returns_split_streams(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'video.f1080.mp4').write_bytes(b'video')
            (root / 'video.faudio.mp4').write_bytes(b'audio')
            with self.assertRaisesRegex(RuntimeError, '合并'):
                final_media(root / 'absent.jsonl', root, 'unused')

    def test_bad_ffmpeg_fails_before_download(self):
        with self.assertRaisesRegex(RuntimeError, 'FFmpeg'):
            require_ffmpeg({'FFMPEG_BINARY': '/missing/ffmpeg-for-test'})

    def test_real_stream_checks_and_only_final_artifact(self):
        ffmpeg = require_ffmpeg({})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / 'complete.mp4'
            silent = root / 'silent.mp4'
            subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'color=size=32x32:rate=10',
                '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=22050', '-t', '0.3',
                '-c:v', 'mpeg4', '-c:a', 'aac', str(video)], check=True, capture_output=True)
            subprocess.run([ffmpeg, '-v', 'error', '-i', str(video), '-an', '-c:v', 'copy', str(silent)],
                check=True, capture_output=True)
            (root / 'old.faudio.mp4').write_bytes(b'old component')
            manifest = root / 'final.jsonl'
            info = {'filepath': str(video), 'acodec': 'aac', 'vcodec': 'mpeg4'}
            manifest.write_text(json.dumps(info), encoding='utf-8')
            self.assertEqual(final_media(manifest, root, ffmpeg), [video.resolve()])
            info['filepath'] = str(silent)
            manifest.write_text(json.dumps(info), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, '音轨'):
                final_media(manifest, root, ffmpeg)
            info['acodec'] = 'none'
            manifest.write_text(json.dumps(info), encoding='utf-8')
            self.assertEqual(final_media(manifest, root, ffmpeg), [silent.resolve()])


if __name__ == '__main__':
    unittest.main()
