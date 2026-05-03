import pytest

from creational_patterns.simple_factory import Bike, Car, Truck, VehicleFactory, VehicleType


def test_vehicle_factory_returns_correct_types() -> None:
    assert isinstance(VehicleFactory.create_vehicle(VehicleType.CAR), Car)
    assert isinstance(VehicleFactory.create_vehicle(VehicleType.BIKE), Bike)
    assert isinstance(VehicleFactory.create_vehicle(VehicleType.TRUCK), Truck)


def test_vehicle_factory_accepts_string_aliases() -> None:
    assert VehicleFactory.create_vehicle("car").describe() == "Car"


def test_vehicle_factory_invalid() -> None:
    with pytest.raises(ValueError):
        VehicleFactory.create_vehicle("boat")
