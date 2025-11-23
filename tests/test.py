import os
import sys
import difflib
import contextlib
import logging
from unittest.mock import NonCallableMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from codexctl.device import HardwareType, DeviceManager
from codexctl.updates import UpdateManager
from codexctl import Manager

# Mock device manager object, only the `logger` field is accessed by `set_server_config`
device_manager = NonCallableMock(["logger"])

set_server_config = DeviceManager.set_server_config
codexctl = Manager(device="reMarkable2", logger=logging.getLogger(__name__))
updater = UpdateManager(logger=logging.getLogger(__name__))

from io import StringIO
from io import BytesIO

FAILED = False
UPDATE_FILE_PATH = ".venv/2.15.1.1189_reMarkable2-wVbHkgKisg-.signed"

assert os.path.exists(UPDATE_FILE_PATH), "Update image missing"

class BufferWriter:
    def __init__(self, buffer):
        self._buffer = buffer

    def write(self, data):
        self._buffer.write(data)


class BufferBytesIO(BytesIO):
    @property
    def buffer(self):
        return BufferWriter(self)


def assert_value(msg, value, expected):
    global FAILED
    print(f"Testing {msg}: ", end="")
    if value == expected:
        print("pass")
        return

    FAILED = True
    print("fail")
    print(f"  {value} != {expected}")


def assert_gt(msg, value, expected):
    global FAILED
    print(f"Testing {msg}: ", end="")
    if value >= expected:
        print("pass")
        return

    FAILED = True
    print("fail")
    print(f"  {value} != {expected}")

@contextlib.contextmanager
def assert_raises(msg, expected):
    global FAILED
    print(f"Testing {msg}: ", end="")
    try:
        yield
        got = "no exception"
    except expected:
        print("pass")
        return
    except Exception as e:
        got = e.__class__.__name__

    FAILED = True
    print("fail")
    print(f"  {got} != {expected.__name__}")

def test_set_server_config(original, expected):
    global FAILED
    print("Testing set_server_config: ", end="")
    result = set_server_config(device_manager, original, "test")
    if result == expected:
        print("pass")
        return

    FAILED = True
    print("fail")
    for diff in difflib.ndiff(
        expected.splitlines(keepends=True), result.splitlines(keepends=True)
    ):
        print(f"  {diff}")


def test_ls(path, expected):
    global FAILED
    global UPDATE_FILE_PATH
    print(f"Testing ls {path}: ", end="")
    with contextlib.redirect_stdout(StringIO()) as f:
        try:
            codexctl.call_func("ls", {'file': UPDATE_FILE_PATH, 'target_path': path})

        except SystemExit:
            pass

    result = f.getvalue()
    if result == expected:
        print("pass")
        return

    FAILED = True
    print("fail")
    for diff in difflib.ndiff(
        expected.splitlines(keepends=True), result.splitlines(keepends=True)
    ):
        print(f"  {diff}")


def test_cat(path, expected):
    global FAILED
    global UPDATE_FILE_PATH
    print(f"Testing cat {path}: ", end="")
    with contextlib.redirect_stdout(BufferBytesIO()) as f:
        try:
            codexctl.call_func("cat", {'file': UPDATE_FILE_PATH, 'target_path': path})
        except SystemExit:
            pass

    result = f.getvalue()
    if result == expected:
        print("pass")
        return

    FAILED = True
    print("fail")
    for diff in difflib.ndiff(
        expected.decode("utf-8").splitlines(keepends=True),
        result.decode("utf-8").splitlines(keepends=True),
    ):
        print(f"  {diff}")


test_set_server_config(
    "",
    "SERVER=test\n",
)

test_set_server_config(
    """[General]
#REMARKABLE_RELEASE_APPID={98DA7DF2-4E3E-4744-9DE6-EC931886ABAB}
#SERVER=https://updates.cloud.remarkable.engineering/service/update2
#GROUP=Prod
#PLATFORM=reMarkable2
REMARKABLE_RELEASE_VERSION=3.9.5.2026
""",
    """[General]
SERVER=test
#REMARKABLE_RELEASE_APPID={98DA7DF2-4E3E-4744-9DE6-EC931886ABAB}
#SERVER=https://updates.cloud.remarkable.engineering/service/update2
#GROUP=Prod
#PLATFORM=reMarkable2
REMARKABLE_RELEASE_VERSION=3.9.5.2026
""",
)

test_set_server_config(
    """[General]
SERVER=testing
#REMARKABLE_RELEASE_APPID={98DA7DF2-4E3E-4744-9DE6-EC931886ABAB}
#SERVER=https://updates.cloud.remarkable.engineering/service/update2
#GROUP=Prod
#PLATFORM=reMarkable2
REMARKABLE_RELEASE_VERSION=3.9.5.2026
""",
    """[General]
SERVER=test
#SERVER=testing
#REMARKABLE_RELEASE_APPID={98DA7DF2-4E3E-4744-9DE6-EC931886ABAB}
#SERVER=https://updates.cloud.remarkable.engineering/service/update2
#GROUP=Prod
#PLATFORM=reMarkable2
REMARKABLE_RELEASE_VERSION=3.9.5.2026
""",
)

test_ls(
    "/",
    ". .. lost+found bin boot dev etc home lib media mnt postinst proc run sbin sys tmp uboot-postinst uboot-version usr var\n",
)
test_ls(
    "/mnt",
    ". ..\n",
)

test_cat("/etc/version", b"20221026104022\n")

assert_value("latest rm1 version", updater.get_latest_version(HardwareType.RM1), "3.23.0.64")
assert_value("latest rm2 version", updater.get_latest_version(HardwareType.RM2), "3.23.0.64")
# Don't think this test is needed.

assert_gt(
    "toltec rm1 version",
    updater.get_toltec_version(HardwareType.RM1),
    "3.3.2.1666"
)
assert_gt(
    "toltec rm2 version",
    updater.get_toltec_version(HardwareType.RM2),
    "3.3.2.1666"
)
with assert_raises("toltec rmpp version", SystemExit):
    updater.get_toltec_version(HardwareType.RMPP)

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
