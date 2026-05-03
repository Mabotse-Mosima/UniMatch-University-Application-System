from decimal import Decimal

from creational_patterns.factory_method import CreditCardProcessor, PayPalProcessor


def test_credit_card_processor_creates_payment_result() -> None:
    p = CreditCardProcessor()
    assert p.process_payment(Decimal("10.00")) == "credit-card:10.00"


def test_paypal_processor_initialization_path() -> None:
    p = PayPalProcessor()
    assert p.process_payment(Decimal("5")) == "paypal:5"
