from creational_patterns.prototype import Circle, Rectangle, ShapeCache


def test_shape_prototype_clones_circle() -> None:
    original = Circle(5)
    clone = original.clone()
    assert original.radius == clone.radius
    assert clone is not original


def test_shape_cache_returns_independent_clones() -> None:
    cache = ShapeCache()
    cache.put("small", Rectangle(2, 3))
    a = cache.get("small")
    b = cache.get("small")
    assert a.width == b.width == 2
    assert a is not b
