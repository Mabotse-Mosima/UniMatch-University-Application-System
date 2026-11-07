import pytest

from creational_patterns.builder import PizzaBuilder


def test_pizza_builder_sets_attributes() -> None:
    pizza = PizzaBuilder().add_cheese().add_toppings("pepperoni", "olives").build()
    assert pizza.cheese is True
    assert pizza.toppings == ["pepperoni", "olives"]


def test_pizza_builder_rejects_empty_configuration() -> None:
    with pytest.raises(ValueError):
        PizzaBuilder().build()
