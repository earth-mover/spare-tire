"""Third Wheel - A tool to rename Python wheel packages for multi-version installation."""

from third_wheel.patch import patch_wheel
from third_wheel.rename import rename_wheel

__version__ = "0.1.0"
__all__ = ["patch_wheel", "rename_wheel"]
