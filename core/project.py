# -*- coding: utf-8 -*-

import json
from pathlib import Path

from alias import *
from core.build import BuildConfig, Builder, Compiler
from core.graphics import IComponentGraphics
from core.kit import Kit, KitManager
from core.meta import SupportedLanguage
from core.script import Script
from path import BASE_DIR


@final
class Project:
    # Canonical extension of project archives written by ``save`` / read by ``load``
    Extension: Final[string] = '.ecproj'

    def __init__(self, name: string, lang: SupportedLanguage):
        self.name = name
        self.path: Nullable[string] = null
        self.required_kits: IList[Kit] = []
        self.target_lang: SupportedLanguage = lang
        self.scripts: IList[Script] = []
        # The C standard the project compiles against: it decides the language
        # rules of the static checking (the keyword sets, see ``core.checker``);
        # supported values: c89, c99, c11, c17, c23
        self.c_standard: string = 'c99'
        self._dirty: bool = False

    def __serialize__(self) -> IDictionary[string, Any]:
        return {
            'name': self.name,
            'required_kits': [serialize(kit) for kit in self.required_kits],
            'target_lang': serialize(self.target_lang),
            'scripts': [serialize(script) for script in self.scripts],
            'c_standard': self.c_standard,
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], kit_manager: KitManager,
                graphics: IComponentGraphics) -> Self:
        """
        Restore a project from its serialization.
        Counterpart of ``__serialize__``; scripts carry component trees, whose
        restoration requires the UI context (graphics) of a canvas.

        **Attention**: Restored ``required_kits`` field is of type IList[string],
        and requires further ``Kit`` resolution.
        """
        if not isinstance(data, dict):
            raise SerializationError(f'Cannot deserialize {data} to Project: invalid type')
        require_member(data, 'name', 'required_kits', 'target_lang', 'scripts')
        name = data['name']
        require_type(name, string)
        lang = deserialize(SupportedLanguage, data['target_lang'])
        require_type(data['required_kits'], list)
        require_type(data['scripts'], list)
        proj = Project(name, lang)
        proj.scripts = [Script.restore(script, kit_manager, graphics) for script in data['scripts']]
        proj.required_kits = [kit for kit in data['required_kits']]
        # 'c_standard' is absent in archives made before the setting existed
        c_standard = data.get('c_standard', 'c99')
        if isinstance(c_standard, string) and c_standard.strip():
            proj.c_standard = c_standard.strip()
        return proj

    def save(self, path: string | Path) -> void:
        """
        Write the project to a ``.ecproj`` archive on disk.
        Counterpart of ``load``; bridges ``__serialize__`` to the file system.
        :param path: target file path of the archive
        :except OSError: raise when the file cannot be written
        """
        path = Path(path)
        with path.open('w', encoding='utf-8') as file:
            json.dump(serialize(self), file, ensure_ascii=False, indent=4)
        self.path = str(path)
        self.clear_dirty()

    @classmethod
    def load(cls, path: string | Path, kit_manager: KitManager,
             graphics: IComponentGraphics) -> Self:
        """
        Read a project from a ``.ecproj`` archive on disk.
        Counterpart of ``save``; bridges the file system to ``restore``.
        :param path: path of the archive to read
        :param kit_manager: kit manager used to resolve the component types
        :param graphics: graphics interface of the canvas the scripts are restored on
        :return: the loaded project, with ``path`` set and the dirty state cleared
        :except SerializationError: raise when the file is not a valid project archive
        :except OSError: raise when the file cannot be read
        """
        path = Path(path)
        try:
            with path.open('r', encoding='utf-8') as file:
                data = json.load(file)
        except json.JSONDecodeError as e:
            raise SerializationError(f'Invalid project file {path}: {e}') from e
        proj = cls.restore(data, kit_manager, graphics)
        proj.path = str(path)
        proj.clear_dirty()
        return proj

    def add_script(self, script: Script) -> void:
        """
        Add a script to the project (idempotent).
        :param script: script to add
        """
        if script not in self.scripts:
            self.scripts.append(script)
            self._dirty = True

    def remove_script(self, script: Script) -> void:
        """
        Remove a script from the project.
        :param script: script to remove
        :except ValueError: raise when the script does not belong to the project
        """
        self.scripts.remove(script)
        self._dirty = True

    def create_script(self, display_name: string, root_component: string,
                      kit_manager: KitManager, graphics: IComponentGraphics) -> Script:
        """
        Create a script around a fresh root component and add it to the project.
        :param display_name: name the UI shows for the script (tabs, palette)
        :param root_component: complete name of the root component type
            (in format 'kit.component'); it must act as a root
        :param kit_manager: kit manager used to resolve the component type
        :param graphics: graphics interface of the canvas the script lives on
        :return: the created script, already appended to ``scripts``
        :except TypeError: raise when the component does not act as a root
        """
        tu = kit_manager.create_component(null, graphics, root_component)
        script = Script(tu)
        script.display_name = display_name
        self.add_script(script)
        return script

    @property
    def is_dirty(self) -> bool:
        """Whether the project itself or any of its scripts changed since the
        last save (or since creation/loading, when nothing was saved yet)."""
        return self._dirty or any(script.is_dirty for script in self.scripts)

    def mark_dirty(self) -> void:
        """Record that the project changed outside the script-management API."""
        self._dirty = True

    def clear_dirty(self) -> void:
        """Reset the dirty state of the project and all its scripts
        (called after the project was persisted)."""
        self._dirty = False
        for script in self.scripts:
            script.clear_dirty()

    def build_script(self, script: Script, config: BuildConfig) -> Compiler:
        """
        Compile a script of the project.
        :param script: script to compile
        :param config: building configuration
        :return: the compiler holding the compilation products
        """
        compiler = Compiler(config)
        script.build(compiler)
        return compiler

    def build_project(self, config: BuildConfig) -> tuple[IList[Path], IList[Builder.BuildWarning]]:
        """
        Compile every script of the project and write the compilation products to files.
        :param config: building configuration; its ``output`` directory receives the
            artifacts, defaulting to ``build`` next to the project file (or under the
            workspace ``build`` directory, named after the project, while unsaved)
        :return: paths of the generated artifacts and the warnings the compilers
            raised along the way (the artifacts are still written)
        """
        if config.output is not null:
            output = config.output
        elif self.path is not null:
            output = Path(self.path).parent / 'build'
        else:
            output = BASE_DIR / 'build' / self.name
        output.mkdir(parents=True, exist_ok=True)
        artifacts: IList[Path] = []
        warnings: IList[Builder.BuildWarning] = []
        for script in self.scripts:
            compiler = self.build_script(script, config)
            warnings.extend(compiler.warnings)
            fragments: IList[string] = compiler.products.get(config.target_lang.id, [])
            target = output / f'{script.name}.{config.target_lang.extension}'
            with Compiler.CompilationProductGuide(str(target)) as product:
                product.write('\n\n'.join(fragments))
            artifacts.append(target)
        return artifacts, warnings
