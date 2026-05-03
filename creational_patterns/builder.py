from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Pizza:
    cheese: bool = False
    toppings: list[str] = field(default_factory=list)


class PizzaBuilder:
    """Builds a Pizza step-by-step with optional ingredients."""

    def __init__(self) -> None:
        self._pizza = Pizza()

    def add_cheese(self) -> PizzaBuilder:
        self._pizza.cheese = True
        return self

    def add_toppings(self, *items: str) -> PizzaBuilder:
        self._pizza.toppings.extend(items)
        return self

    def build(self) -> Pizza:
        if not self._pizza.cheese and not self._pizza.toppings:
            raise ValueError("Pizza must have cheese or at least one topping")
        return self._pizza
