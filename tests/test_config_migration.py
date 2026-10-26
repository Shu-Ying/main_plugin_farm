import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "farm_config_migration",
    ROOT / "integrations/zhenxun/config_migration.py",
)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class ConfigMigrationTests(unittest.TestCase):
    def test_zhenxun_registers_quality_and_resource_configuration(self):
        plugin = ModuleType('nonebot.plugin')
        plugin.PluginMetadata = lambda **values: SimpleNamespace(**values)
        utils = ModuleType('zhenxun.configs.utils')
        utils.Command = lambda **values: SimpleNamespace(**values)
        utils.RegisterConfig = lambda **values: SimpleNamespace(**values)
        utils.PluginExtraData = lambda **values: SimpleNamespace(
            to_dict=lambda: values,
        )
        package = ModuleType('quality_metadata_fixture')
        package.__path__ = []
        version = ModuleType(package.__name__ + '._version')
        version.__version__ = '0.0.0'
        runtime = ModuleType(package.__name__ + '.runtime')
        runtime.COMMANDS, runtime.HELP = {}, ''
        commands = ModuleType(package.__name__ + '.commands')
        modules = {m.__name__: m for m in (
            plugin, utils, package, version, runtime, commands,
        )}
        source = ROOT / 'integrations/zhenxun/__init__.py'
        namespace = {'__package__': package.__name__}
        with patch.dict(sys.modules, modules):
            exec(compile(source.read_text(encoding='utf-8'), str(source),
                         'exec'), namespace)
        configs = namespace['__plugin_meta__'].extra['configs']
        self.assertEqual(len(configs), 3)
        by_key = {config.key: config for config in configs}
        self.assertEqual(set(by_key), {
            '农场图片质量', '资源获取地址', 'farm_service 地址',
        })
        for key, expected, value_type in (
            ('农场图片质量', 75, int),
            ('资源获取地址', 'Github', str),
            ('farm_service 地址', '', str),
        ):
            with self.subTest(key=key):
                self.assertEqual(by_key[key].value, expected)
                self.assertEqual(by_key[key].default_value, expected)
                self.assertIs(by_key[key].type, value_type)

    @unittest.skipUnless(importlib.util.find_spec('pydantic'),
                         'NoneBot host config requires Pydantic')
    def test_nonebot_quality_config_is_strict_and_bounded(self):
        libraries = [importlib.import_module('pydantic')]
        try:
            libraries.append(importlib.import_module('pydantic.v1'))
        except ImportError:
            pass
        for library in libraries:
            with self.subTest(library=library.__name__):
                spec = importlib.util.spec_from_file_location(
                    'farm_nonebot_quality_config',
                    ROOT / 'integrations/nonebot/config.py',
                )
                module = importlib.util.module_from_spec(spec)
                with patch.dict(sys.modules, {'pydantic': library}):
                    spec.loader.exec_module(module)
                config = module.Config
                self.assertEqual(config().farm_image_quality, 75)
                self.assertEqual(config().farm_resource_source, 'Github')
                self.assertEqual(config().farm_service_url, '')
                self.assertEqual(str(config(
                    farm_data_dir='existing-custom-data',
                ).farm_data_dir), 'existing-custom-data')
                self.assertIsNone(config(farm_data_dir='').farm_data_dir)
                for source in ('Github', 'Gitea', 'farm_service'):
                    selected = config(
                        farm_resource_source=source,
                        farm_service_url='https://farm.example/service',
                    )
                    self.assertEqual(selected.farm_resource_source, source)
                    self.assertEqual(selected.farm_service_url,
                                     'https://farm.example/service')
                for source in ('github', 'unknown', '', None):
                    with self.subTest(source=source), self.assertRaises(
                        library.ValidationError,
                    ):
                        config(farm_resource_source=source)
                for value in (1, 95):
                    actual = config(farm_image_quality=value).farm_image_quality
                    self.assertEqual(actual, value)
                for value in (0, 96, True, '75', 75.5):
                    with self.subTest(value=value), self.assertRaises(
                        library.ValidationError,
                    ):
                        config(farm_image_quality=value)

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
