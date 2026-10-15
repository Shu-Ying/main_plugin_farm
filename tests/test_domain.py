import json
from pathlib import Path
import unittest

from farm_core import Catalogue, FarmError, Identity
from farm_core.domain import (
    MAX_VALUE, Plant, boosted, level_for,
)


class DomainTests(unittest.TestCase):
    def test_integer_level_boundaries(self):
        for level in (0, 1, 2, 50, 1000000):
            threshold = 100 * level * (level + 1)
            self.assertEqual(level_for(threshold), level)
            if level:
                self.assertEqual(level_for(threshold - 1), level - 1)
        self.assertGreater(level_for(MAX_VALUE), 0)

    def test_per_plot_bonus_is_order_independent(self):
        plots = [(20, 100), (30, 50), (17, 10)]
        first = sum(boosted(*plot) for plot in plots)
        second = sum(boosted(*plot) for plot in reversed(plots))
        self.assertEqual(first, 103)
        self.assertEqual(first, second)

    def test_bool_and_out_of_range_values_are_not_integers(self):
        for value in (True, False, -1, 1.5, MAX_VALUE + 1):
            with self.subTest(value=value):
                with self.assertRaises(FarmError):
                    level_for(value)

    def test_explicit_identity_encoding_does_not_collide(self):
        first = Identity("a", "b:c", "d", "e")
        second = Identity("a:b", "c", "d", "e")
        self.assertNotEqual(first.key, second.key)
        with self.assertRaises(FarmError):
            Identity("a", "", "qq", "1")

    def test_bundled_catalogue_matches_all_source_rows(self):
        root = Path(__file__).resolve().parents[1]
        document = json.loads(
            (root / "src/farm_core/data/plants.json").read_bytes()
        )
        catalogue = Catalogue.bundled()
        self.assertEqual(len(catalogue), 202)
        for row in document["plants"]:
            expected = Plant.from_legacy(row)
            self.assertEqual(catalogue.get(row["name"]), expected)
        self.assertEqual(catalogue.get("胡萝卜").growth_seconds, 13 * 3600)

    def test_corrupt_catalogue_is_rejected(self):
        for content in (
            b"not json", b"{}", b'{"schema":true,"plants":[]}',
            b'{"schema":2,"plants":[]}',
        ):
            with self.subTest(content=content):
                with self.assertRaises(FarmError):
                    Catalogue.loads(content)

    def test_invalid_and_duplicate_plants_are_rejected(self):
        plant = next(iter(Catalogue.bundled()))
        with self.assertRaises(FarmError):
            Catalogue([plant, plant])
        with self.assertRaises(FarmError):
            Catalogue.bundled().get("不存在")
        with self.assertRaises(FarmError):
            Plant(1, "bad", 0, -1, False, 0, 1, 1, 1, 1, 1, 1)


if __name__ == "__main__":
    unittest.main()
