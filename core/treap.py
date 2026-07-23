# -*- coding: utf-8 -*-

import random

from alias import *

_NonRotTreapTy = TypeVar('_NonRotTreapTy', SupportsEq, SupportsGt, SupportsAddSub, IValueContainer)


class NonRotationalTreap(Generic[_NonRotTreapTy, U]):
    """
    Non-rotational treap for value-storage types.
    """

    class _Node:
        __slots__ = ('value', 'priority', 'left', 'right', 'lazy_delta')

        def __init__(self, value: _NonRotTreapTy, zero_delta: U):
            self.value: _NonRotTreapTy = value
            self.priority: float = random.random()
            self.left: Nullable[NonRotationalTreap[_NonRotTreapTy, U]._Node] = null
            self.right: Nullable[NonRotationalTreap[_NonRotTreapTy, U]._Node] = null
            self.lazy_delta: U = zero_delta

    def __init__(self, element_type: typeof[_NonRotTreapTy], zero: U, unit: U):
        self._root: Nullable = null
        self._zero: U = zero
        self._unit: U = unit
        self.element_type: typeof[_NonRotTreapTy] = element_type

    def _create_node(self, value: _NonRotTreapTy) -> _Node:
        return NonRotationalTreap._Node(value, self._zero)

    def _push_down(self, _FHQTreapTy: Nullable[_Node]) -> void:
        """
        Propagate the lazy add tag of the node down to its children.
        :param _FHQTreapTy: node that carries lazy add tag
        """
        if _FHQTreapTy is null or _FHQTreapTy.lazy_delta == self._zero:
            return
        delta: U = _FHQTreapTy.lazy_delta
        if _FHQTreapTy.left is not null:
            _FHQTreapTy.left.value += delta
            _FHQTreapTy.left.lazy_delta += delta
        if _FHQTreapTy.right is not null:
            _FHQTreapTy.right.value += delta
            _FHQTreapTy.right.lazy_delta += delta
        _FHQTreapTy.lazy_delta = self._zero

    def _split(self, root: Nullable[_Node], k: _NonRotTreapTy) -> tuple[Nullable[_Node], Nullable[_Node]]:
        """
        Split the treap into two treaps:
        one containing elements no greater than the given value,
        the other containing elements greater than the given value.
        :param root: the root node of the treap to split
        :param k: the split key
        :return: the two children treaps
        """
        if not has_value(k):
            if valueof(k) == float('inf'):
                return root, null
            else:
                return null, root

        if root is null:
            return null, null
        self._push_down(root)
        if root.value > k:
            a, b = self._split(root.left, k)
            root.left = b
            return a, root
        else:
            a, b = self._split(root.right, k)
            root.right = a
            return root, b

    def _merge(self, a: Nullable[_Node], b: Nullable[_Node]) -> Nullable[_Node]:
        """
        Merge two treaps when maximum in `a` is less than minimum in `b`.
        :param a: treap containing elements of less values
        :param b: treap containing elements of greater values
        :return: the merged treap
        """
        if a is null:
            return b
        if b is null:
            return a
        if a.priority > b.priority:
            self._push_down(a)
            a.right = self._merge(a.right, b)
            return a
        else:
            self._push_down(b)
            b.left = self._merge(a, b.left)
            return b

    def _inorder(self, root: Nullable[_Node]) -> IEnumerable[_NonRotTreapTy]:
        """
        Perform an in-order traversal of the treap and push down lazy add tags.
        :param root: the root node of the treap
        :return: a generator that yields nodes in ascending order
        """
        if root is null:
            return
        self._push_down(root)
        yield from self._inorder(root.left)
        yield root.value
        yield from self._inorder(root.right)

    def _find(self, t: Nullable[_Node], x: _NonRotTreapTy) -> Nullable[_Node]:
        """
        Find the node that contains the specified value.
        :param t: the root node of the treap to search
        :param x: the specified value
        :return: the node if found, null otherwise

        **Attention**: this method accepts argument of generic type `_NonRotTreapTy`, which means the element type of the
        container. If searching for element by valueof(x), use `_find_by_value` instead.
        """
        if t is null:
            return null
        self._push_down(t)
        if x == t.value:
            return t
        elif x < t.value:
            return self._find(t.left, x)
        else:
            return self._find(t.right, x)

    def _find_by_value(self, t: Nullable[_Node], v: U) -> Nullable[_Node]:
        """
        Find the node that contains a value, valueof() of which equalizes to the specified value.
        :param t: the root node of the treap to search
        :param v: the specified value
        :return: the node if found, null otherwise

        This method requires element type (generic type `_NonRotTreapTy`) follows `IValueContainer` protocol,
        i.e. has `__value__() -> T` method.

        **Attention**: this method accepts argument of generic type `U`, which means the valueof() type of the elements.
        If searching for element by original value, use `_find` instead.
        """
        if t is null:
            return null
        self._push_down(t)
        if v == valueof(t.value):
            return t
        elif valueof(t.value) < v:
            return self._find_by_value(t.right, v)
        else:
            return self._find_by_value(t.left, v)

    def _value_to_element(self, t: _Node, v: U) -> Nullable[_NonRotTreapTy]:
        """
        Find an element that contains the specified value.
        :param t: the root node of child treap to search
        :param v: the specified value
        :return: the element if found, null otherwise
        """
        node = self._find_by_value(t, v)
        return node.value if node is not null else null

    def _floor(self, t: _Node, v: U) -> Nullable[_NonRotTreapTy]:
        """
        Find the element that contains the minimum value among those no less than the specified.
        :param t: the root node of child treap to search
        :param v: the specified value
        :return: the element if found, `maximum(_NonRotTreapTy)` otherwise
        """
        if t is null:
            return maximum(self.element_type)
        self._push_down(t)
        if valueof(t.value) == v:
            return t.value
        elif valueof(t.value) < v:
            return self._floor(t.right, v)
        else:
            return self._floor(t.left, v)

    def _ceil(self, t: _Node, v: U) -> Nullable[_NonRotTreapTy]:
        """
        Find the element that contains the maximum value among those no greater than the specified.
        :param t: the root node of child treap to search
        :param v: the specified value
        :return: the element if found, `minimum(_NonRotTreapTy)` otherwise
        """
        if t is null:
            return minimum(self.element_type)
        self._push_down(t)
        if valueof(t.value) == v:
            return t.value
        elif valueof(t.value) > v:
            return self._ceil(t.left, v)
        else:
            return self._ceil(t.right, v)

    def insert(self, x: _NonRotTreapTy) -> void:
        """
        Insert an element into the treap.
        :param x: element to insert
        """
        node = self._create_node(x)
        a, b = self._split(self._root, x)
        self._root = self._merge(self._merge(a, node), b)

    def remove(self, x: _NonRotTreapTy) -> bool:
        """
        Remove an element from the treap.
        :param x: element to remove
        :return: if the element exists in the treap, return `True`; return `False` otherwise
        """
        a, b = self._split(self._root, x)
        a1, a2 = self._split(a, x - self._unit)
        if a2 is null:
            self._root = self._merge(self._merge(a1, a2), b)
            return False
        new_a2 = self._merge(a2.left, a2.right)
        self._root = self._merge(self._merge(a1, new_a2), b)
        return True

    def query(self, l: _NonRotTreapTy, r: _NonRotTreapTy) -> IEnumerable[_NonRotTreapTy]:
        """
        Query all the elements in interval [l, r].
        :param l: lower bound of the interval
        :param r: upper bound of the interval
        :return: a generator that yields the found elements
        """
        a, b = self._split(self._root, r)
        a1, a2 = self._split(a, l - self._unit)
        res: IEnumerable[_NonRotTreapTy] = self._inorder(a2)
        self._root = self._merge(self._merge(a1, a2), b)
        return res

    def query_by_value(self, l: U, r: U) -> IEnumerable[_NonRotTreapTy]:
        """
        Query all the elements in interval [valueof(l), valueof(r)].
        :param l: lower bound of the interval
        :param r: upper bound of the interval
        :return: a generator that yields the found elements
        """
        a, b = self._split(self._root, self._ceil(self._root, r))
        a1, a2 = self._split(a, self._ceil(a, l - self._unit))
        res: IEnumerable[_NonRotTreapTy] = self._inorder(a2)
        self._root = self._merge(self._merge(a1, a2), b)
        return res

    def find(self, v: U) -> Nullable[_NonRotTreapTy]:
        """
        Find the element with value equal to valueof() of the specified value.
        :param v: the specified value
        :return: the element if found, null otherwise
        """
        node = self._find_by_value(self._root, v)
        if node is null:
            return null
        return node.value

    def add_suffix(self, left: _NonRotTreapTy, delta: U) -> void:
        """
        Add a delta value to all nodes greater than the specified threshold.
        :param left: the threshold
        :param delta: the delta value to add
        """
        a, b = self._split(self._root, left)
        if b is not null:
            b.value += delta
            b.lazy_delta += delta
        self._root = self._merge(a, b)

    def add_suffix_by_value(self, left: U, delta: U) -> void:
        """
        Add a delta value to all nodes that contain values greater than the specified threshold.
        :param left: the threshold
        :param delta: the delta value to add
        """
        t: _NonRotTreapTy = self.find(left)
        if t is not null:
            self.add_suffix(t, delta)

    @staticmethod
    def create_integral(element_type: typeof[_NonRotTreapTy]) -> 'NonRotationalTreap[_NonRotTreapTy, int]':
        return NonRotationalTreap(element_type, 0, 1)
