import ext4
import warnings
import errno
import libconf

from remarkable_update_image import UpdateImage
from remarkable_update_image import UpdateImageSignatureException
from remarkable_update_image.cpio import Archive
from typing import Tuple, Optional, Dict
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


def get_swu_metadata(swu_file: str) -> Tuple[str, HardwareType]:
    """
    Extract version and hardware type from an SWU file.

    Args:
        swu_file: Path to the SWU file

    Returns:
        Tuple of (version, hardware_type)

    Raises:
        ValueError: If sw-description is missing or invalid
        SystemError: If hardware type is unsupported
    """
    archive = Archive(swu_file)
    archive.open()
    try:
        if b"sw-description" not in archive.keys():
            raise ValueError(f"Not a valid SWU file: {swu_file}")

        sw_desc = archive["sw-description"].read().decode("utf-8")
        info = libconf.loads(sw_desc)["software"]

        version = info.get("version")
        if not version:
            raise ValueError(f"No version found in sw-description: {swu_file}")

        if "reMarkable1" in info:
            hardware = HardwareType.RM1
        elif "reMarkable2" in info:
            hardware = HardwareType.RM2
        elif "ferrari" in info:
            hardware = HardwareType.RMPP
        elif "chiappa" in info:
            hardware = HardwareType.RMPPM
        else:
            raise SystemError(f"Unsupported hardware type in SWU file: {swu_file}")

        return version, hardware
    finally:
        archive.close()


def extract_swu_files(
    swu_file: str,
    output_dir: Optional[str] = None,
    filter_files: Optional[list] = None
) -> Optional[Dict[str, bytes]]:
    """
    Extract files from an SWU (CPIO) archive.

    Args:
        swu_file: Path to the SWU file
        output_dir: Directory to extract files to (for full extraction to disk)
        filter_files: List of filenames to extract (selective extraction)

    Returns:
        If filter_files is provided: dict mapping filename -> file data (bytes)
        If output_dir is provided: None (files written to disk)
    """
    import os
    from pathlib import Path

    archive = Archive(swu_file)
    archive.open()
    try:
        if output_dir is not None:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            for name in archive.keys():
                if name == b"TRAILER!!!":
                    continue

                filename = name.decode('utf-8')
                file_path = output_path / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)

                with open(file_path, 'wb') as f:
                    f.write(archive[name].read())

            return None

        else:
            extracted = {}

            if filter_files is None:
                for name in archive.keys():
                    if name != b"TRAILER!!!":
                        extracted[name.decode('utf-8')] = archive[name].read()
            else:
                for filename in filter_files:
                    entry = archive.get(filename)
                    if entry:
                        extracted[filename] = entry.read()

            return extracted
    finally:
        archive.close()
