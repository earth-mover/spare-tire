"""Spare Tire - A tool to rename Python wheel packages for multi-version installation."""

from spare_tire.patch import patch_wheel
from spare_tire.rename import rename_wheel

__version__ = "0.1.0"
__all__ = ["patch_wheel", "rename_wheel"]
