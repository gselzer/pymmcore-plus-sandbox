from os import path
from pathlib import Path
from typing import Any

import yaml
from magicgui.widgets import request_values
from pymmcore_plus import CMMCorePlus


class Setting:
    """A pluggable setting for the UI."""

    def __init__(self, mmc: CMMCorePlus | None = None) -> None:
        self._mmc = CMMCorePlus.instance() if not mmc else mmc

    @property
    def name(self) -> str:
        raise NotImplementedError()

    @property
    def default(self) -> Any:
        raise NotImplementedError()

    @property
    def value(self) -> Any:
        raise NotImplementedError()

    @value.setter
    def value(self, v: Any) -> Any:
        raise NotImplementedError()

    def magic_description(self) -> dict[str, Any]:
        """Returns a magicgui widget allowing the user to"""
        raise NotImplementedError()

    def convert_to_yaml(self) -> Any:
        """
        Called by the Settings object to convert this setting value into valid YAML
        """
        raise NotImplementedError()

    def init_from_yaml(self, new_value: Any) -> None:
        """
        Called by the Settings object to initialize this setting with the value
        described in loaded YAML
        """
        raise NotImplementedError()


class DefaultConfigFile(Setting):
    """Setting controlling the startup MM configuration file."""

    def __init__(self, mmc: CMMCorePlus | None = None) -> None:
        super().__init__(mmc)

    @property
    def name(self) -> str:
        return "Startup Configuration File"

    @property
    def default(self) -> Any:
        return None

    @property
    def value(self) -> Any:
        return self._value

    @value.setter
    def value(self, v: Any) -> Any:
        self._value = v

    def magic_description(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "annotation": Path,
            "options": {"label": self.name, "mode": "r", "filter": "*.cfg"},
        }

    def convert_to_yaml(self) -> Any:
        # PyYAML doesn't know how to dump Path objects
        return "" if self._value is None else str(self._value)

    def init_from_yaml(self, yaml_value: Any):
        if yaml_value not in [None, ""]:
            self._value = Path(yaml_value)
            self._mmc.loadSystemConfiguration(yaml_value)
        else:
            self._value = None


SETTINGS_FILE = "settings.yml"


class Settings:
    """Retains a set of configurable Settings used by the UI"""

    def __init__(self, settings: list[Setting] | None = None):
        if settings is None:
            settings = []
        self._settings: list[Setting] = []

        self.saved_values = {}
        # Load configuration settings if present
        if path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE) as cf:
                self.saved_values.update(yaml.safe_load(cf))

        for s in settings:
            self.add(s)

    def add(self, setting: Setting):
        """Adds `setting` to the list of utilized `Setting`s."""
        setting.init_from_yaml(self.saved_values.get(setting.name, setting.default))
        self._settings.append(setting)

    def configure(self):
        """Updates the values of utilized `Setting`s via user-editable `QDialog`."""
        args = {s.name: s.magic_description() for s in self._settings}
        if results := request_values(
            values=args, title="PyMMCore Plus Sandbox Settings"
        ):
            for s in self._settings:
                s.value = results[s.name]

            yaml_results = {s.name: s.convert_to_yaml() for s in self._settings}

            # Save settings
            with open(SETTINGS_FILE, "w") as cf:
                yaml.safe_dump(yaml_results, cf)
