import copy
import hashlib
import json
from io import BytesIO
from zipfile import ZipFile
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from farm_core.catalogue_release import make_manifest, parse_manifest
from farm_render.catalogue_bundle import load_catalogue_release

ROOT = Path(__file__).resolve().parents[1]


def release(price=21, extra=False):
    plants = json.loads((ROOT / 'src/farm_core/data/plants.json').read_bytes())
    plants.pop('source_sha256', None)
    plants['plants'][0]['price'] = price
    metadata = json.loads(
        (ROOT / 'src/farm_render/data/metadata.json').read_bytes()
    )
    if extra:
        row = copy.deepcopy(plants['plants'][0])
        row.update(id=9001, name='更新测试作物')
        plants['plants'].append(row)
        metadata['plants'][row['name']] = copy.deepcopy(
            metadata['plants'][plants['plants'][0]['name']]
        )
    files = {
        'plants.json': json.dumps(plants, ensure_ascii=False).encode(),
        'metadata.json': json.dumps(metadata, ensure_ascii=False).encode(),
        **{name: (ROOT / 'src/farm_render/data' / name).read_bytes()
           for name in ('assets.zip', 'land-soils.zip')},
    }
    return make_manifest(files, 'test-v1'), files


class CatalogueReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifest, self.files = release(price=99)

    def tearDown(self):
        self.temp.cleanup()

    def fetch(self, url, limit):
        if url.endswith('/manifest.json'):
            data = json.dumps(self.manifest).encode()
        else:
            self.assertIn('/releases/' + self.manifest['release'] + '/', url)
            data = self.files[url.rsplit('/', 1)[-1]]
        self.assertLessEqual(len(data), limit)
        return data

    def load(self, **kwargs):
        return load_catalogue_release(self.root, **kwargs)

    def test_new_catalogue_and_metadata_activate_as_one_version(self):
        with patch('farm_render.catalogue_bundle._fetch',
                   side_effect=self.fetch):
            result = self.load()
        self.assertEqual(result.catalogue.get_by_id(1).price, 99)
        self.assertEqual(result.origin, 'remote')
        self.assertTrue(result.bundle_path.is_file())
        self.assertTrue(result.soils_path.is_file())
        current = json.loads((self.root / 'catalogue/current.json').read_bytes())
        self.assertEqual(current['release'], self.manifest['release'])

    def test_404_reuses_verified_current(self):
        with patch('farm_render.catalogue_bundle._fetch',
                   side_effect=self.fetch):
            self.load()
        with patch('farm_render.catalogue_bundle._fetch',
                   side_effect=OSError('404')):
            result = self.load()
        self.assertEqual(result.catalogue.get_by_id(1).price, 99)
        self.assertEqual(result.origin, 'cache')

    def test_wrong_bytes_do_not_replace_current(self):
        with patch('farm_render.catalogue_bundle._fetch',
                   side_effect=self.fetch):
            self.load()
        before = (self.root / 'catalogue/current.json').read_bytes()
        self.manifest, self.files = release(price=100)
        self.files['plants.json'] = b'broken'
        with patch('farm_render.catalogue_bundle._fetch',
                   side_effect=self.fetch):
            result = self.load()
        self.assertEqual(result.catalogue.get_by_id(1).price, 99)
        self.assertEqual((self.root / 'catalogue/current.json').read_bytes(),
                         before)

    def test_first_offline_start_uses_bootstrap_without_images(self):
        with patch('farm_render.catalogue_bundle._fetch',
                   side_effect=OSError('offline')):
            result = self.load()
        self.assertEqual(result.origin, 'bootstrap')
        self.assertEqual(len(result.catalogue), 202)
        self.assertFalse((self.root / 'catalogue/current.json').exists())

    def test_cache_loss_with_unknown_player_id_refuses_start(self):
        with patch('farm_render.catalogue_bundle._fetch',
                   side_effect=OSError('offline')):
            with self.assertRaisesRegex(ValueError, 'catalogue.*ID'):
                self.load(required_ids={9001})

    def test_incompatible_downgrade_keeps_added_crop(self):
        self.manifest, self.files = release(extra=True)
        with patch('farm_render.catalogue_bundle._fetch',
                   side_effect=self.fetch):
            self.load()
        self.manifest, self.files = release()
        with patch('farm_render.catalogue_bundle._fetch',
                   side_effect=self.fetch):
            result = self.load()
        self.assertEqual(result.catalogue.get_by_id(9001).name, '更新测试作物')
        self.assertEqual(result.origin, 'cache')

    def test_manifest_rejects_bool_unknown_schema_paths_and_fingerprint(self):
        for key, value in [('schema', True), ('schema', 2),
                           ('release', '0' * 64)]:
            bad = copy.deepcopy(self.manifest)
            bad[key] = value
            with self.assertRaises(ValueError):
                parse_manifest(json.dumps(bad).encode())
        bad = copy.deepcopy(self.manifest)
        bad['files']['../file'] = bad['files'].pop('assets.zip')
        with self.assertRaises(ValueError):
            parse_manifest(json.dumps(bad).encode())

    def test_selected_service_prefix_is_respected(self):
        seen = []
        def fetch(url, limit):
            seen.append(url)
            return self.fetch(url, limit)
        with patch('farm_render.catalogue_bundle._fetch', side_effect=fetch):
            self.load(source='farm_service',
                      service_url='https://farm.test/prefix')
        self.assertTrue(all(
            url.startswith('https://farm.test/prefix/v1/catalogue/')
            for url in seen
        ))

    def test_current_matching_remote_still_checks_player_ids(self):
        with patch('farm_render.catalogue_bundle._fetch',
                   side_effect=self.fetch):
            self.load()
            with self.assertRaisesRegex(ValueError, 'catalogue.*ID'):
                self.load(required_ids={9001})

    def test_consistent_but_invalid_metadata_keeps_current(self):
        with patch('farm_render.catalogue_bundle._fetch',
                   side_effect=self.fetch):
            self.load()
            self.files['metadata.json'] = b'{"schema":1,"canvas":[0,0]}'
            self.manifest = make_manifest(self.files, 'bad-layout')
            result = self.load()
        self.assertEqual(result.origin, 'cache')
        self.assertEqual(result.metadata['canvas'], [3072, 1872])

    def test_huge_coordinate_keeps_verified_current(self):
        with patch('farm_render.catalogue_bundle._fetch',
                   side_effect=self.fetch):
            self.load()
            metadata = json.loads(self.files['metadata.json'])
            metadata['positions'][0]['x'] = 10 ** 500
            self.files['metadata.json'] = json.dumps(metadata).encode()
            self.manifest = make_manifest(self.files, 'huge-coordinate')
            result = self.load()
        self.assertEqual(result.origin, 'cache')
        self.assertLess(result.metadata['positions'][0]['x'], 10000000)

    def test_removing_old_crop_image_is_rejected_even_with_valid_hashes(self):
        with patch('farm_render.catalogue_bundle._fetch',
                   side_effect=self.fetch):
            self.load()
            metadata = json.loads(self.files['metadata.json'])
            name = next(key for key in metadata['images']
                        if key.startswith('plant/'))
            metadata['images'].pop(name)
            output = BytesIO()
            with ZipFile(BytesIO(self.files['assets.zip'])) as old, \
                    ZipFile(output, 'w') as new:
                for item in old.infolist():
                    if item.filename != name:
                        new.writestr(item, old.read(item))
            self.files['assets.zip'] = output.getvalue()
            self.files['metadata.json'] = json.dumps(metadata).encode()
            self.manifest = make_manifest(self.files, 'missing-image')
            result = self.load()
        self.assertEqual(result.origin, 'cache')
        self.assertIn(name, result.metadata['images'])
