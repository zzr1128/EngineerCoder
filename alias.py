# -*- coding: utf-8 -*-

import abc
import collections
from types import TracebackType
from typing import *

from multipledispatch import dispatch

T = TypeVar('T')
U = TypeVar('U')
P = ParamSpec('P')
R = TypeVar('R')

type void = Literal[None]
null = None
type Nullable[T] = T | null
type typeof[expr] = type[expr]
type IEnumerable[T] = Iterable[T]
type IEnumerator[T] = Iterator[T]
string = str
type ICollection[T] = collections.abc.Collection[T]
type IList[T] = collections.abc.MutableSequence[T]
type IReadOnlyList[T] = collections.abc.Sequence[T]
type IDictionary[TKey, TValue] = collections.abc.MutableMapping[TKey, TValue]
type IReadOnlyDictionary[TKey, TValue] = collections.abc.Mapping[TKey, TValue]
HashSet = set
type Queue[T] = collections.deque[T]
type Stack[T] = list[T]
type Array[T] = list[T]
type Predicate[T] = Callable[[T], bool]
type Task[T] = Awaitable[T]
type ValueTask[T] = Awaitable[T]

abstract = abc.ABC
pure_virtual = abc.abstractmethod


class IValueContainer[T](Protocol):
    def __value__(self) -> T: ...

    @classmethod
    def __minimum__(cls) -> T: ...

    @classmethod
    def __maximum__(cls) -> T: ...

    def __has_value__(self) -> bool: ...


def valueof(obj: IValueContainer[T]) -> T:
    return obj.__value__()


def has_value(obj: IValueContainer[T]) -> bool:
    return obj.__has_value__()


def minimum(tp: typeof[IValueContainer[T]]) -> IValueContainer[T]:
    return tp.__minimum__()


def maximum(tp: typeof[IValueContainer[T]]) -> IValueContainer[T]:
    return tp.__maximum__()


class SupportsEq(Protocol):
    def __eq__(self, other: Self) -> bool: ...


class SupportsGt(Protocol):
    def __gt__(self, other: Self) -> bool: ...


class SupportsAddSub[U](Protocol):
    def __add__(self, other: U) -> Self: ...
    def __sub__(self, other: U) -> Self: ...


class IDisposable(abstract):
    _disposed = False

    def __enter__(self) -> 'IDisposable':
        return self

    def __exit__(self, exc_type: Nullable[typeof[BaseException]], exc_val: Nullable[BaseException],
                 exc_tb: Nullable[TracebackType]) -> bool:
        self._disposed = True
        self.Dispose()
        return exc_type is None  # Throw exceptions upwards

    def __del__(self) -> void:
        if not self._disposed:
            self.Dispose()

    @pure_virtual
    def Dispose(self) -> void:
        pass


class ISignal(Protocol):
    def connect(self, slot: Callable[P, R]) -> void:
        pass

    def disconnect(self, slot: Callable[P, R]) -> void:
        pass


class Delegate(Generic[P, R]):
    def __init__(self, signal: Nullable[ISignal]):
        self.signal = signal
        self.callbacks = []

    def __iadd__(self, callback: Callable[P, R]) -> void:
        if self.signal is not null:
            self.signal.connect(callback)
        self.callbacks.append(callback)

    def __isub__(self, callback: Callable[P, R]) -> void:
        if self.signal is not null:
            self.signal.disconnect(callback)
        self.callbacks.remove(callback)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return_value = null
        for callback in self.callbacks:
            return_value = callback(*args, **kwargs)
        return return_value


# noinspection PyUnusedLocal
def maybe_unused(*args: Any) -> void:
    return


def dispatch_method(*types: typeof[object] | tuple[typeof[object], ...]) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        disp = dispatch(object, *types)
        wrapped = disp(func)
        def wrapper(self, *args: P.args, **kwargs: P.kwargs) -> R:
            maybe_unused(self)
            return wrapped(*args, **kwargs)
        return wrapper
    return decorator
