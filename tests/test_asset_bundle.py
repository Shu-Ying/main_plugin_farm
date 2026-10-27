from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from farm_render import bundle

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / 'src/farm_render/data/assets.zip'


class BundleTests(unittest.TestCase):
    def test_manifest_check_without_third_party_packages(self):
        result = subprocess.run(
            [sys.executable, '-S',
             str(ROOT / 'scripts/check_asset_manifest.py')],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Verified external asset manifest', result.stdout)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.expected = bundle.expected_manifest()

    def download(self, url, destination, limit):
        content = ZIP.read_bytes()
        self.assertEqual(limit, len(content))
        destination.write(content)

    def test_download_deduplicates_and_cache_hash_checked_each_start(self):
        with patch.object(bundle, '_copy_remote',
                          side_effect=self.download) as fetch:
            with ThreadPoolExecutor(4) as pool:
                results = list(pool.map(
                    lambda _: bundle.ensure_assets(self.root), range(4),
                ))
            self.assertEqual(len(set(results)), 1)
            self.assertEqual(fetch.call_count, 1)
            path = results[0]
            content = bytearray(path.read_bytes())
            content[-1] ^= 1
            path.write_bytes(content)
            bundle.ensure_assets(self.root)
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(path.read_bytes(), ZIP.read_bytes())

    def test_gitea_and_service_use_service_repository_and_configured_base(self):
        with patch.object(bundle, '_copy_remote',
                          side_effect=self.download) as fetch:
            bundle.ensure_assets(self.root / 'gitea', 'Gitea')
            self.assertEqual(fetch.call_args.args[0],
                'https://gitea.diuse.work/Diuse/farm_service/'
                'raw/branch/main/catalogue/releases/'
                + self.expected['catalogue_release'] + '/assets.zip')
            bundle.ensure_assets(self.root / 'service', 'farm_service',
                                 'https://farm.example/prefix/')
            self.assertEqual(fetch.call_args.args[0],
                'https://farm.example/prefix/v1/catalogue/releases/'
                + self.expected['catalogue_release'] + '/assets.zip')

    def test_failed_download_leaves_no_partial_and_wrong_hash_is_rejected(self):
        def corrupt(url, destination, limit):
            data = bytearray(ZIP.read_bytes())
            data[-1] ^= 1
            destination.write(data)
        with patch.object(bundle, '_copy_remote', side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                bundle.ensure_assets(self.root)
        self.assertFalse(list(self.root.rglob('assets.zip')))
        self.assertFalse(list(self.root.rglob('*.download')))
        with patch.object(bundle, '_copy_remote', side_effect=OSError()):
            with self.assertRaises(OSError):
                bundle.ensure_assets(self.root)
        self.assertFalse(list(self.root.rglob('*.download')))

    def test_invalid_source_and_service_configuration(self):
        for source, url in [('unknown', ''), ('farm_service', ''),
                            ('farm_service', 'http://farm.example'),
                            ('Github', 'https://user:pass@farm.example'),
                            ('Gitea', 'https://farm.example/?token=secret')]:
            with self.subTest(source=source, url=url):
                with self.assertRaises(ValueError):
                    bundle.ensure_assets(self.root, source, url)

    def test_download_enforces_response_limit_and_https_redirect(self):
        class Response(BytesIO):
            headers = {'Content-Length': '20'}
            def geturl(self):
                return 'https://farm.example/assets.zip'
        with patch.object(bundle, 'urlopen', return_value=Response(b'x'*20)):
            with self.assertRaisesRegex(ValueError, 'limit'):
                bundle._copy_remote('https://farm.example/a', BytesIO(), 10)
        response = Response(b'')
        response.geturl = lambda: 'http://farm.example/a'
        with patch.object(bundle, 'urlopen', return_value=response):
            with self.assertRaises(ValueError):
                bundle._copy_remote('https://farm.example/a', BytesIO(), 10)

    def test_download_reports_throttled_progress_without_urls(self):
        class Response(BytesIO):
            headers = {'Content-Length': '262144'}
            def geturl(self):
                return 'https://farm.example/private/assets.zip'
        with patch.object(bundle, 'urlopen', return_value=Response(
                b'x' * 262144)), patch.object(
                    bundle.time, 'monotonic',
                    side_effect=[0, 0.2, 1.1, 1.2, 2.2]), \
                self.assertLogs(bundle.logger, level='INFO') as captured:
            bundle._copy_remote('https://farm.example/private/assets.zip',
                                BytesIO(), 262144)
        messages = '\n'.join(captured.output)
        self.assertIn('下载开始', messages)
        self.assertIn('50.0%', messages)
        self.assertIn('100.0%', messages)
        self.assertIn('下载完成', messages)
        self.assertEqual(messages.count('下载进度'), 2)
        self.assertNotIn('farm.example', messages)
        self.assertNotIn('private', messages)

    def test_unknown_length_and_failed_download_report_truthfully(self):
        class Response(BytesIO):
            headers = {}
            def geturl(self):
                return 'https://farm.example/a'
        with patch.object(bundle, 'urlopen', return_value=Response(b'abc')), \
                patch.object(bundle.time, 'monotonic', side_effect=[0, 1.1]), \
                self.assertLogs(bundle.logger, level='INFO') as captured:
            bundle._copy_remote('https://farm.example/a', BytesIO(), 10)
        self.assertIn('下载完成', '\n'.join(captured.output))
        self.assertIn('已下载', '\n'.join(captured.output))
        self.assertNotIn('%', '\n'.join(captured.output))
        with patch.object(bundle, 'urlopen', side_effect=OSError('secret')), \
                self.assertLogs(bundle.logger, level='INFO') as captured:
            with self.assertRaises(OSError):
                bundle._copy_remote('https://farm.example/a', BytesIO(), 10)
        messages = '\n'.join(captured.output)
        self.assertIn('下载失败', messages)
        self.assertNotIn('下载完成', messages)
        self.assertNotIn('secret', messages)
