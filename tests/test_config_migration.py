import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "farm_config_migration",
    ROOT / "integrations/zhenxun/config_migration.py",
)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class ConfigMigrationTests(unittest.TestCase):
    def test_cleanup_backups_and_repeat_are_scoped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            group = SimpleNamespace(configs={
                "绘制农场清晰度": "low", "CUSTOM": "keep",
            })
            saves = []
            manager = SimpleNamespace(
                file=root / "plugins2config.yaml",
                _simple_file=root / "config.yaml",
                _simple_data={
                    "farm": {"绘制农场清晰度": "low", "CUSTOM": "keep"},
                    "other": {"服务地址": "keep"},
                },
                get=lambda module: group,
                save=lambda **kwargs: saves.append(kwargs),
            )
            for path in (manager.file, manager._simple_file):
                path.write_text("original", encoding="utf-8")
            migration.migrate_config(manager, "farm")
            self.assertEqual(group.configs, {"CUSTOM": "keep"})
            self.assertEqual(manager._simple_data["farm"], {"CUSTOM": "keep"})
            self.assertEqual(manager._simple_data["other"], {"服务地址": "keep"})
            self.assertEqual(saves, [{"save_simple_data": True}])
            for path in (manager.file, manager._simple_file):
                self.assertEqual(path.with_name(
                    path.name + ".farm-v1.bak",
                ).read_text(encoding="utf-8"), "original")
            migration.migrate_config(manager, "farm")
            self.assertEqual(len(saves), 1)
