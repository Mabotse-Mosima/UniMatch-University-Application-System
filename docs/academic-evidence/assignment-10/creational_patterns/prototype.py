from __future__ import annotations

import copy
from abc import ABC, abstractmethod


class Shape(ABC):
    @abstractmethod
    def clone(self) -> Shape:
        raise NotImplementedError


class Circle(Shape):
    def __init__(self, radius: float) -> None:
        self.radius = radius

    def clone(self) -> Circle:
        return copy.deepcopy(self)


class Rectangle(Shape):
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height

    def clone(self) -> Rectangle:
        return copy.deepcopy(self)


class ShapeCache:
    """Stores pre-configured prototypes and returns independent clones."""

    def __init__(self) -> None:
        self._cache: dict[str, Shape] = {}

    def put(self, key: str, shape: Shape) -> None:
        self._cache[key] = shape

    def get(self, key: str) -> Shape:
        if key not in self._cache:
            raise KeyError(key)
        return self._cache[key].clone()
