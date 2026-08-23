# -*- coding: utf-8 -*-
"""
Headless check of the project persistence layer:

- ``Project.save`` writes a ``.ecproj`` archive and ``Project.load`` reads it
  back, round-tripping the serialized scripts and component trees;
- the script management API (``create_script`` / ``add_script`` /
  ``remove_script``) keeps ``Project.scripts`` consistent;
- the dirty tracking (``is_dirty`` / ``mark_dirty`` / ``clear_dirty``) clears
  on save/load and aggregates the script-level flags;
- ``Script.display_name`` falls back to the file stem, then 'untitled', and
  archives made before display names existed still restore.
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

from alias import *
from core.environment import Environment
from core.project import Project
from core.script import Script
from kits.fluent.fluent import UDF
from vce_serialize_check import _CanvasStub, _GraphicsStub


def main() -> void:
    app = QApplication(sys.argv)
    env = Environment()
    env.import_kit(os.path.join(_root, 'kits', 'cbased'))
    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))
    kit_manager = env.kit_manager

    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / f'demo{Project.Extension}'

        # 1. create_script builds a root component, appends it and marks dirty
        project = Project('demo', UDF)
        assert not project.is_dirty, 'fresh project must not be dirty'
        script = project.create_script('init-case', 'fluent.translation_unit',
                                       kit_manager, graphics)
        assert project.scripts == [script], 'create_script must append the script'
        assert script.display_name == 'init-case', script.display_name
        assert project.is_dirty, 'create_script must mark the project dirty'

        # 2. add_script is idempotent
        project.add_script(script)
        assert project.scripts == [script], 'add_script must stay idempotent'

        # 3. save/load round trip preserves the archive and resets the path
        project.save(archive)
        assert archive.exists(), 'save must write the archive'
        assert project.path == str(archive), project.path
        assert not project.is_dirty, 'save must clear the dirty state'

        loaded = Project.load(archive, kit_manager, graphics)
        assert serialize(loaded) == serialize(project), 'load must round-trip the archive'
        assert loaded.path == str(archive), loaded.path
        assert not loaded.is_dirty, 'load must start clean'
        assert loaded.scripts[0].display_name == 'init-case'
        print('save/load round trip ok')

        # 4. dirty tracking aggregates the script flags and clears on save
        loaded.scripts[0].mark_dirty()
        assert loaded.is_dirty, 'script dirtiness must surface on the project'
        loaded.save(archive)
        assert not loaded.is_dirty and not loaded.scripts[0].is_dirty
        print('dirty tracking ok')

        # 5. UTF-8 display names survive the JSON archive
        unicode_script = project.create_script('初始化用例', 'fluent.translation_unit',
                                               kit_manager, graphics)
        project.save(archive)
        reloaded = Project.load(archive, kit_manager, graphics)
        assert reloaded.scripts[-1].display_name == '初始化用例'
        print('unicode display name ok')

        # 6. remove_script drops the script and rejects foreign ones
        project.remove_script(unicode_script)
        assert unicode_script not in project.scripts
        try:
            project.remove_script(unicode_script)
            raise AssertionError('removing a foreign script must fail')
        except ValueError:
            pass
        print('script removal ok')

        # 7. display_name falls back to the file stem, then 'untitled'
        anon = Script(kit_manager.create_component(null, graphics, 'fluent.translation_unit'))
        assert anon.display_name == 'untitled', anon.display_name
        anon.path = Path('solver.ecs')
        assert anon.display_name == 'solver', anon.display_name
        print('display name fallback ok')

        # 8. archives made before display names existed still restore
        sdata = serialize(script)
        del sdata['display_name']
        legacy = Script.restore(sdata, kit_manager, graphics)
        assert legacy.display_name == 'untitled', legacy.display_name
        print('legacy archive ok')

        # 9. malformed archives raise SerializationError
        bad = Path(tmp) / f'bad{Project.Extension}'
        bad.write_text('{not json', encoding='utf-8')
        try:
            Project.load(bad, kit_manager, graphics)
            raise AssertionError('malformed archive must be rejected')
        except SerializationError:
            pass
        print('malformed archive rejection ok')

    # 10. the repository's test project loads
    legacy_project = Project.load(os.path.join(_root, 'test.ecproj'), kit_manager, graphics)
    assert legacy_project.name == '未命名' and len(legacy_project.scripts) >= 1
    print('repository test project loads ok')

    print('ALL PASSED')


if __name__ == '__main__':
    main()
