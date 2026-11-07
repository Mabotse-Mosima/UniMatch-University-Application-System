from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal


class PaymentProcessor(ABC):
    """Creator interface: subclasses supply concrete payment handling."""

    @abstractmethod
    def process_payment(self, amount: Decimal) -> str:
        raise NotImplementedError


class CreditCardProcessor(PaymentProcessor):
    def process_payment(self, amount: Decimal) -> str:
        return f"credit-card:{amount}"


class PayPalProcessor(PaymentProcessor):
    def process_payment(self, amount: Decimal) -> str:
        return f"paypal:{amount}"
