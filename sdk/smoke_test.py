# -*- coding: utf-8 -*-
"""
Startup smoke test: boots the real application off-screen and asserts the
main window constructs without raising. Purpose-built to catch constructor
crashes (e.g. the null-graphics regression) before they reach delivery.
Must finish well under 10 seconds.
"""

import os
import sys
import time
import traceback

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
if sys.stdout.encoding not in (None, 'utf-8', 'UTF-8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)  # kits are imported via relative paths
for _sub in (_ROOT, os.path.join(_ROOT, 'core'), os.path.join(_ROOT, 'interface'),
             os.path.join(_ROOT, 'sdk')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

CORE_MODULES = (
    'core.arch',
    'core.build',
    'core.checker',
    'core.completer',
    'core.component',
    'core.environment',
    'core.graphics',
    'core.hyper_text_edit',
    'core.kit',
    'core.localization',
    'core.meta',
    'core.project',
    'core.resource',
    'core.script',
    'core.signature',
    'core.theme',
    'core.treap',
    'interface.editor',
    'interface.editor_tab_widget',
    'interface.visual_code_edit',
    'interface.component_palette',
    'interface.edition_canvas',
)


def main() -> int:
    start = time.perf_counter()

    import importlib
    for module_name in CORE_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception:
            print(f'FAILED: cannot import {module_name}')
            traceback.print_exc()
            return 1
    print(f'imports ok ({len(CORE_MODULES)} modules)')

    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)

    from interface.editor import EditorWindow
    try:
        window = EditorWindow()
    except Exception:
        print('FAILED: EditorWindow constructor raised')
        traceback.print_exc()
        return 1

    try:
        window.show()
        app.processEvents()
        assert window.env.project is not None, 'project must exist at startup'
        assert len(window.env.project.scripts) >= 1, 'default script expected'
        assert len(window.tabs) == len(window.env.project.scripts), \
            'every script must own a canvas'
    except Exception:
        print('FAILED: window not usable after construction')
        traceback.print_exc()
        return 1
    finally:
        window.close()

    elapsed = time.perf_counter() - start
    if elapsed > 10:
        print(f'FAILED: smoke test too slow ({elapsed:.1f}s > 10s)')
        return 1

    print(f'EditorWindow constructed and shown off-screen in {elapsed:.1f}s')
    print('SMOKE TEST PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
