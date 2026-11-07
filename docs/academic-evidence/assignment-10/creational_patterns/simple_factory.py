from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum


class VehicleType(Enum):
    CAR = "car"
    BIKE = "bike"
    TRUCK = "truck"


class Vehicle(ABC):
    @abstractmethod
    def describe(self) -> str:
        raise NotImplementedError


class Car(Vehicle):
    def describe(self) -> str:
        return "Car"


class Bike(Vehicle):
    def describe(self) -> str:
        return "Bike"


class Truck(Vehicle):
    def describe(self) -> str:
        return "Truck"


class VehicleFactory:
    """Centralizes creation of concrete vehicles."""

    @staticmethod
    def create_vehicle(kind: VehicleType | str) -> Vehicle:
        if isinstance(kind, str):
            kind = VehicleType(kind.lower())
        if kind == VehicleType.CAR:
            return Car()
        if kind == VehicleType.BIKE:
            return Bike()
        if kind == VehicleType.TRUCK:
            return Truck()
        raise ValueError(f"Unknown vehicle type: {kind}")
