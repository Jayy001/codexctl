import ext4
import warnings
import errno

from remarkable_update_image import UpdateImage
from remarkable_update_image import UpdateImageSignatureException
from .device import HardwareType


def get_update_image(file: str):
    """Extracts files from an update image (<3.11 currently)"""

    image = UpdateImage(file)
    volume = ext4.Volume(image, offset=0)
    try:
        inode = volume.inode_at("/usr/share/update_engine/update-payload-key.pub.pem")
        if inode is None:
            raise FileNotFoundError()

        inode.verify()
        image.verify(inode.open().read())

    except UpdateImageSignatureException:
        warnings.warn("Signature doesn't match contents", RuntimeWarning)

    except FileNotFoundError:
        warnings.warn("Public key missing", RuntimeWarning)

    except OSError as e:
        if e.errno != errno.ENOTDIR:
            raise
        warnings.warn("Unable to open public key", RuntimeWarning)

    return image, volume


def get_swu_metadata(swu_file: str) -> tuple[str, HardwareType]:
    """
    Extract version and hardware type from an SWU file.

    Args:
        swu_file: Path to the SWU file

    Returns:
        Tuple of (version, hardware_type)

    Raises:
        SystemError: If hardware type is unsupported
    """
    image = UpdateImage(swu_file)

    hw_map = {
        "reMarkable1": HardwareType.RM1,
        "reMarkable2": HardwareType.RM2,
        "ferrari": HardwareType.RMPP,
        "chiappa": HardwareType.RMPPM,
    }

    if image.hardware_type not in hw_map:
        raise SystemError(f"Unsupported hardware type in SWU file: {swu_file}")

    return image.version, hw_map[image.hardware_type]
