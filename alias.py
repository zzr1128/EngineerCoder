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
type Queue = collections.deque
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
    # pyrefly: ignore [bad-return]
    return tp.__minimum__()


def maximum(tp: typeof[IValueContainer[T]]) -> IValueContainer[T]:
    # pyrefly: ignore [bad-return]
    return tp.__maximum__()


class SupportsEq(Protocol):
    # pyrefly: ignore [bad-override]
    def __eq__(self, other: Self) -> bool: ...


class SupportsGt(Protocol):
    def __gt__(self, other: Self) -> bool: ...


class SupportsAddSub[U](Protocol):
    def __add__(self, other: U) -> Self: ...
    def __sub__(self, other: U) -> Self: ...


class Serializable(Protocol):
    def __serialize__(self) -> Any: ...

    @classmethod
    def __deserialize__(cls, data: Any) -> Any: ...


class SerializationError(Exception):
    pass


_SerializableTy = TypeVar('_SerializableTy', bound=Serializable)


def serialize(obj: Serializable) -> Any:
    return obj.__serialize__()


def deserialize(cls: typeof[_SerializableTy], data: Any) -> _SerializableTy:
    return cls.__deserialize__(data)


def require_member(ser: IDictionary[string, Any], *keys) -> void:
    missing = [key for key in keys if key not in ser]
    if missing:
        raise SerializationError(f"Missing fields: {', '.join(missing)}")


def require_type(obj: Any, tp: type, name: Nullable[string] = null) -> void:
    if not isinstance(obj, tp):
        if name is null:
            name = obj.__name__
        raise SerializationError(f'Field {name} requires type {tp.__name__}')


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

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R | null:
        return_value = null
        for callback in self.callbacks:
            return_value = callback(*args, **kwargs)
        return return_value


def NotNull(obj: Nullable[T]) -> T:
    assert obj is not null, 'Null reference'
    return obj


# noinspection PyUnusedLocal
def maybe_unused(*args: Any) -> void:
    """
    Mark a variable intentionally unused and remove warnings by static analyzers.
    :param args: variables that are maybe unused
    """
    return


def unreachable() -> NoReturn:
    raise RuntimeError('Executing unreachable code')


def dispatch_method(*types: typeof[object] | tuple[typeof[object], ...]) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(func: Callable[P, R]) -> Callable[..., R]:
        disp = dispatch(object, *types)
        wrapped = disp(func)
        def wrapper(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
            maybe_unused(self)
            return wrapped(*args, **kwargs)
        return wrapper
    return decorator
