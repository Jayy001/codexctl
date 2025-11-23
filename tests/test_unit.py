import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from codexctl.updates import UpdateManager

FAILED = False


def assert_value(msg, value, expected):
    global FAILED
    print(f"Testing {msg}: ", end="")
    if value == expected:
        print("pass")
        return

    FAILED = True
    print("fail")
    print(f"  {value} != {expected}")


assert_value(
    "boundary cross 3.23->3.20",
    UpdateManager.is_bootloader_boundary_downgrade("3.23.0.64", "3.20.0.92"),
    True
)
assert_value(
    "boundary cross 3.22->3.20",
    UpdateManager.is_bootloader_boundary_downgrade("3.22.0.64", "3.20.0.92"),
    True
)
assert_value(
    "no boundary 3.23->3.22",
    UpdateManager.is_bootloader_boundary_downgrade("3.23.0.64", "3.22.0.64"),
    False
)
assert_value(
    "no boundary 3.20->3.19",
    UpdateManager.is_bootloader_boundary_downgrade("3.20.0.92", "3.19.0.82"),
    False
)
assert_value(
    "upgrade 3.20->3.22",
    UpdateManager.is_bootloader_boundary_downgrade("3.20.0.92", "3.22.0.64"),
    False
)
assert_value(
    "same version 3.22->3.22",
    UpdateManager.is_bootloader_boundary_downgrade("3.22.0.64", "3.22.0.64"),
    False
)
assert_value(
    "empty string current",
    UpdateManager.is_bootloader_boundary_downgrade("", "3.20.0.92"),
    False
)
assert_value(
    "non-numeric version",
    UpdateManager.is_bootloader_boundary_downgrade("abc.def", "3.20.0.92"),
    False
)

if FAILED:
    sys.exit(1)
