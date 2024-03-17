import sys
import difflib
import codexctl

FAILED = False


def test_set_server_config(original, expected):
    global FAILED
    print("Testing set_server_config: ", end="")
    result = codexctl.set_server_config(original, "test")
    if result == expected:
        print("pass")
        return

    FAILED = True
    print("fail")
    for diff in difflib.ndiff(expected.splitlines(), result.splitlines()):
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

if FAILED:
    sys.exit(1)
