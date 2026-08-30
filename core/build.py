# -*- coding:utf-8 -*-

from dataclasses import dataclass
from io import BufferedWriter
from pathlib import Path
from types import TracebackType

from alias import *
from core.localization import _
from core.meta import SupportedLanguage


@dataclass
class BuildConfig:
    class OptimizationLevel:
        O0 = 0x00  # No optimization
        O1 = 0x10  # Basic optimization
        O2 = 0x20  # Standard optimization
        O3 = 0x30  # Aggressive optimization

    target_lang: SupportedLanguage
    opt_level: OptimizationLevel = OptimizationLevel.O0
    # Directory receiving the build artifacts; null lets the project resolve a default
    output: Nullable[Path] = null

    def __serialize__(self) -> IDictionary[string, Any]:
        return {
            'target_lang': serialize(self.target_lang),
            'opt_level': self.opt_level,
            'output': str(self.output) if self.output is not null else null,
        }

    @classmethod
    def __deserialize__(cls, data: IDictionary[string, Any]) -> Self:
        require_member(data, 'target_lang', 'opt_level')
        target_lang = deserialize(SupportedLanguage, data['target_lang'])
        opt_level = data['opt_level']
        require_type(opt_level, int, 'opt_level')
        output_ = data.get('output', null)
        output = Path(output_) if isinstance(output_, string) and output_.strip() else null
        return cls(target_lang, opt_level, output)


class Builder:
    @dataclass
    class BuildErrorCode:
        name: string
        message: string

    class BuildWarning(Warning):
        def __init__(self, code: 'Builder.BuildErrorCode', *texts):
            self.code: string = code.name
            self.texts: tuple = texts  # The positional texts the message was formatted with
            self.message: string = code.message.format(*texts)

        def __str__(self):
            return f'{self.code}: {self.message}'

    class BuildError(Exception):
        def __init__(self, code: 'Builder.BuildErrorCode', *texts):
            self.code: string = code.name
            self.texts: tuple = texts  # The positional texts the message was formatted with
            self.message: string = code.message.format(*texts)

        def __str__(self):
            return f'{self.code}: {self.message}'

    # Placeholder indices are 0-based (``str.format``); every code message may
    # reference the positional texts the raise site supplies
    B1001 = BuildErrorCode('B1001', _('B1001'))  # Unresolved building exception.
    B1002 = BuildErrorCode('B1002', _('B1002'))  # Invalid building configuration: {0}
    B1003 = BuildErrorCode('B1003', _('B1003'))  # I/O exception during building: {0}
    B1004 = BuildErrorCode('B1004', _('B1004'))  # Language "{0}" not supported by component "{1}"
    B1005 = BuildErrorCode('B1005', _('B1005'))  # Multiple components "{1}" conflict for language "{0}"
    B1006 = BuildErrorCode('B1006', _('B1006'))  # Static checking rejected the contents:\n{0}
    B1007 = BuildErrorCode('B1007', _('B1007'))  # The generated code may not pass C compilation:\n{0}

    def __init__(self, config: BuildConfig):
        self.config = config
        self.warnings: IList[Builder.BuildWarning] = []
        self.errors: IList[Builder.BuildError] = []


class Compiler(Builder):
    class CompileWarning(Builder.BuildWarning):
        pass

    class CompileError(Builder.BuildError):
        pass

    class CompilationProductGuide:
        def __init__(self, name: string):
            self.name = name
            self.file: Nullable[BufferedWriter] = null

        def __enter__(self) -> Self:
            try:
                self.file = open(self.name, 'wb')
            except OSError as exc:
                maybe_unused(exc)
                raise Builder.BuildError(Builder.B1003, _('CPG.enter.open_fail').format(self.name))
            return self

        def __exit__(self, exc_type: Nullable[typeof[BaseException]], exc_val: Nullable[BaseException],
                     exc_tb: Nullable[TracebackType]) -> null | bool:
            if self.file is not null and not self.file.closed:
                self.file.close()

        @overload
        def write(self, data: bytes) -> void: ...

        @overload
        def write(self, data: string) -> void: ...

        def write(self, data: bytes | string) -> void:
            if self.file is null or self.file.closed:
                raise Builder.BuildError(Builder.B1003, _('CPG.write.closed').format(self.name))
            if isinstance(data, string):
                data = data.encode(encoding='utf-8')
            try:
                self.file.write(data)
            except OSError as exc:
                maybe_unused(exc)
                raise Builder.BuildError(Builder.B1003, _('CPG.write.fail').format(self.name))


    def __init__(self, config: BuildConfig):
        super().__init__(config)
        self.products: IDictionary[string, Any] = {}
