from io import BytesIO
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


class HelpPackageTests(unittest.TestCase):
    def test_prepared_workflow_image_is_used_and_wrong_platform_rejected(self):
        from build_zhenxun import build
        from help_image import build_help_image
        from verify_zhenxun import read_package
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            prepared = folder / 'help-zhenxun.png'
            content = build_help_image(ROOT, 'zhenxun')
            prepared.write_bytes(content)
            with patch('help_image.subprocess',
                       SimpleNamespace(run=Mock())) as regenerate:
                archive = build(ROOT, folder / 'built', help_image=prepared)
                regenerate.run.assert_not_called()
            self.assertEqual(
                read_package(archive)['images/help-zhenxun.png'], content,
            )
            with self.assertRaisesRegex(ValueError, 'different platform'):
                build_help_image(ROOT, 'astrbot', prepared)

    def test_all_packages_embed_matching_generated_help_and_readme(self):
        import importlib
        with tempfile.TemporaryDirectory() as temporary:
            for platform in ('zhenxun', 'nonebot', 'astrbot'):
                with self.subTest(platform=platform):
                    builder = importlib.import_module('build_' + platform)
                    verifier = importlib.import_module('verify_' + platform)
                    archive = builder.build(ROOT, Path(temporary) / platform)
                    files = verifier.read_package(archive)
                    image_name = f'images/help-{platform}.png'
                    self.assertIn(image_name, files.keys())
                    self.assertIn('./' + image_name,
                                  files['README.md'].decode('utf-8'))
                    for other in ('zhenxun', 'nonebot', 'astrbot'):
                        if other != platform:
                            self.assertNotIn(f'images/help-{other}.png',
                                             files.keys())
                    with Image.open(BytesIO(files[image_name])) as image:
                        self.assertEqual(image.format, 'PNG')
                        self.assertEqual(image.width, 1200)
                        self.assertGreater(image.height, 500)
                        image.verify()
