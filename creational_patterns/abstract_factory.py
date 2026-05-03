from __future__ import annotations

from abc import ABC, abstractmethod


class Button(ABC):
    @abstractmethod
    def render(self) -> str:
        raise NotImplementedError


class WindowsButton(Button):
    def render(self) -> str:
        return "WindowsButton"


class MacOSButton(Button):
    def render(self) -> str:
        return "MacOSButton"


class GUIFactory(ABC):
    @abstractmethod
    def create_button(self) -> Button:
        raise NotImplementedError


class WindowsGUIFactory(GUIFactory):
    def create_button(self) -> Button:
        return WindowsButton()


class MacOSGUIFactory(GUIFactory):
    def create_button(self) -> Button:
        return MacOSButton()
