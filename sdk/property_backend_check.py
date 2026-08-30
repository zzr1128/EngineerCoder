# -*- coding: utf-8 -*-
"""
Headless check of the property-page backend:

- ``KitManager.available_kits`` enumerates the metadata of every imported kit;
- ``Project.available_c_standards`` lists the supported C standards;
- ``Project.build_config`` (optimization level, output directory) survives the
  save/load round trip, and archives made before the setting existed still
  restore with the default configuration.
"""

import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
if sys.stdout.encoding not in (None, 'utf-8', 'UTF-8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface'),
             os.path.join(_root, 'sdk')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from pathlib import Path

from PySide6.QtWidgets import QApplication
from vce_serialize_check import _CanvasStub, _GraphicsStub

from alias import *
from core.build import BuildConfig
from core.environment import Environment
from core.project import Project
from kits.fluent.fluent import UDF


def main() -> void:
    app = QApplication(sys.argv)
    maybe_unused(app)  # Keep the application instance alive during the check
    env = Environment()
    env.import_kit(os.path.join(_root, 'kits', 'cbased'))
    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))
    kit_manager = env.kit_manager

    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)

    # 1. available_kits enumerates the metadata of every imported kit
    infos = kit_manager.available_kits()
    assert len(infos) == 3, f'expected 3 kits, got {len(infos)}'
    names = {info['name'] for info in infos}
    assert names == {'cbased', 'clk', 'fluent'}, names
    for info in infos:
        assert set(info) == {'name', 'display_name', 'description'}, info
        assert info['display_name'].strip(), info
    print('kit enumeration ok')

    # 2. available_c_standards lists the supported standards
    standards = Project.available_c_standards()
    assert standards == ['c89', 'c99', 'c11', 'c17', 'c23'], standards
    print('c standard list ok')

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / f'demo{Project.Extension}'

        # 3. a fresh project carries a default build configuration
        project = Project('demo', UDF)
        assert project.build_config.target_lang == UDF
        assert project.build_config.opt_level == BuildConfig.OptimizationLevel.O0
        assert project.build_config.output is null
        print('default build config ok')

        # 4. BuildConfig serializes and deserializes standalone
        output_dir = Path(tmp) / 'out'
        config = BuildConfig(UDF, BuildConfig.OptimizationLevel.O2, output_dir)
        restored = deserialize(BuildConfig, serialize(config))
        assert restored.target_lang == UDF, restored.target_lang
        assert restored.opt_level == BuildConfig.OptimizationLevel.O2
        assert restored.output == output_dir, restored.output
        print('build config round trip ok')

        # 5. save/load persists the edited configuration with the project
        project.build_config.opt_level = BuildConfig.OptimizationLevel.O3
        project.build_config.output = output_dir
        project.create_script('init-case', 'fluent.translation_unit',
                              kit_manager, graphics)
        project.save(archive)
        loaded = Project.load(archive, kit_manager, graphics)
        assert loaded.build_config.opt_level == BuildConfig.OptimizationLevel.O3
        assert loaded.build_config.output == output_dir
        assert loaded.build_config.target_lang == UDF
        assert serialize(loaded) == serialize(project), 'archive must round-trip'
        print('project build config persistence ok')

        # 6. archives made before the setting existed keep the default config
        legacy_data = serialize(project)
        del legacy_data['build_config']
        legacy = Project.restore(legacy_data, kit_manager, graphics)
        assert legacy.build_config.opt_level == BuildConfig.OptimizationLevel.O0
        assert legacy.build_config.output is null
        print('legacy archive compatibility ok')

    # 7. the repository's test project loads with a default configuration
    legacy_project = Project.load(os.path.join(_root, 'sdk', 'test.ecproj'), kit_manager, graphics)
    assert legacy_project.build_config.target_lang == legacy_project.target_lang
    assert legacy_project.build_config.opt_level == BuildConfig.OptimizationLevel.O0
    print('repository test project ok')

    print('ALL PASSED')


if __name__ == '__main__':
    main()
