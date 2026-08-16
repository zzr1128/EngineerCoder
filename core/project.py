# -*- coding: utf-8 -*-

from pathlib import Path

from alias import *
from core.build import BuildConfig, Compiler
from core.graphics import IComponentGraphics
from core.kit import Kit, KitManager
from core.meta import SupportedLanguage
from core.script import Script
from path import BASE_DIR


@final
class Project:
    def __init__(self, name: string, lang: SupportedLanguage):
        self.name = name
        self.path: Nullable[string] = null
        self.required_kits: IList[Kit] = []
        self.target_lang: SupportedLanguage = lang
        self.scripts: IList[Script] = []

    def __serialize__(self) -> IDictionary[string, Any]:
        return {
            'name': self.name,
            'required_kits': [serialize(kit) for kit in self.required_kits],
            'target_lang': serialize(self.target_lang),
            'scripts': [serialize(script) for script in self.scripts]
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
        return proj

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

    def build_project(self, config: BuildConfig) -> IList[Path]:
        """
        Compile every script of the project and write the compilation products to files.
        :param config: building configuration; its ``output`` directory receives the
            artifacts, defaulting to ``build`` next to the project file (or under the
            workspace ``build`` directory, named after the project, while unsaved)
        :return: paths of the generated artifacts
        """
        if config.output is not null:
            output = config.output
        elif self.path is not null:
            output = Path(self.path).parent / 'build'
        else:
            output = BASE_DIR / 'build' / self.name
        output.mkdir(parents=True, exist_ok=True)
        artifacts: IList[Path] = []
        for script in self.scripts:
            compiler = self.build_script(script, config)
            fragments: IList[string] = compiler.products.get(config.target_lang.id, [])
            target = output / f'{script.name}.{config.target_lang.extension}'
            with Compiler.CompilationProductGuide(str(target)) as product:
                product.write('\n\n'.join(fragments))
            artifacts.append(target)
        return artifacts
