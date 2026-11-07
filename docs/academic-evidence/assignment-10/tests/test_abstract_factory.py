from creational_patterns.abstract_factory import MacOSGUIFactory, WindowsGUIFactory


def test_windows_factory_returns_windows_button() -> None:
    factory = WindowsGUIFactory()
    btn = factory.create_button()
    assert btn.render() == "WindowsButton"


def test_macos_factory_returns_macos_button() -> None:
    factory = MacOSGUIFactory()
    btn = factory.create_button()
    assert btn.render() == "MacOSButton"
