# -*- coding:utf-8 -*-

from dataclasses import dataclass
from io import BufferedWriter
from pathlib import Path
from types import TracebackType

from alias import *
from core.meta import SupportedLanguage
from gettext import gettext as _


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


class Builder:
    @dataclass
    class BuildErrorCode:
        name: string
        message: string

    class BuildWarning(Warning):
        def __init__(self, code: 'Builder.BuildErrorCode', *texts):
            self.code: string = code.name
            self.message: string = code.message.format(*texts)

        def __str__(self):
            return f'{self.code}: {self.message}'

    class BuildError(Exception):
        def __init__(self, code: 'Builder.BuildErrorCode', *texts):
            self.code: string = code.name
            self.message: string = code.message.format(*texts)

        def __str__(self):
            return f'{self.code}: {self.message}'

    B1001 = BuildErrorCode('B1001', _('B1001'))  # Unresolved building exception.
    B1002 = BuildErrorCode('B1002', _('B1002'))  # Invalid building configuration: {1}
    B1003 = BuildErrorCode('B1003', _('B1003'))  # I/O exception during building: {1}
    B1004 = BuildErrorCode('B1004', _('B1004'))  # Language "{1}" not supported by component "{2}"
    B1005 = BuildErrorCode('B1005', _('B1005'))  # Multiple components "{2}" conflict for language "{1}"

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
