import os
import sys
import difflib
import contextlib
import codexctl

from collections import namedtuple
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


def test_set_server_config(original, expected):
    global FAILED
    print("Testing set_server_config: ", end="")
    result = codexctl.set_server_config(original, "test")
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
        Args = namedtuple("Args", "file target_path")
        try:
            codexctl.do_ls(Args(file=UPDATE_FILE_PATH, target_path=path))

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
    print(f"Testing ls {path}: ", end="")
    with contextlib.redirect_stdout(BufferBytesIO()) as f:
        Args = namedtuple("Args", "file target_path")
        try:
            codexctl.do_cat(Args(file=UPDATE_FILE_PATH, target_path=path))

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

codexctl.updateman = codexctl.UpdateManager(logger=codexctl.logger)
assert_value("latest rm1 version", codexctl.version_lookup("latest", 1), "3.11.2.5")
assert_value("latest rm2 version", codexctl.version_lookup("latest", 2), "3.11.2.5")
assert_gt(
    "toltec rm1 version",
    tuple(map(int, codexctl.version_lookup("toltec", 1).split("."))),
    (3, 3, 2),
)
assert_gt(
    "toltec rm2 version",
    tuple(map(int, codexctl.version_lookup("toltec", 2).split("."))),
    (3, 3, 2),
)

if FAILED:
    sys.exit(1)
