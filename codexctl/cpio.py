"""
Pure Python CPIO "newc" format parser for extracting SWU files.
Zero external dependencies - uses only Python stdlib.
"""

import os
import stat
from pathlib import Path
from typing import Dict, Optional, List, Union


def _parse_cpio_header(header_data: bytes) -> Dict[str, int]:
    """
    Parse a CPIO newc format header (110 bytes).

    Format: magic(6) + inode(8) + mode(8) + uid(8) + gid(8) + nlink(8) +
            mtime(8) + filesize(8) + devmajor(8) + devminor(8) +
            rdevmajor(8) + rdevminor(8) + namesize(8) + check(8)

    All fields except magic are 8-digit ASCII hex.
    """
    if len(header_data) != 110:
        raise ValueError(f"Invalid header size: {len(header_data)} (expected 110)")

    header_str = header_data.decode('ascii')
    magic = header_str[0:6]

    if magic != '070702':
        raise ValueError(f"Invalid CPIO magic: {magic} (expected 070702)")

    return {
        'inode': int(header_str[6:14], 16),
        'mode': int(header_str[14:22], 16),
        'uid': int(header_str[22:30], 16),
        'gid': int(header_str[30:38], 16),
        'nlink': int(header_str[38:46], 16),
        'mtime': int(header_str[46:54], 16),
        'filesize': int(header_str[54:62], 16),
        'devmajor': int(header_str[62:70], 16),
        'devminor': int(header_str[70:78], 16),
        'rdevmajor': int(header_str[78:86], 16),
        'rdevminor': int(header_str[86:94], 16),
        'namesize': int(header_str[94:102], 16),
        'check': int(header_str[102:110], 16),
    }


def _align_to_4(offset: int) -> int:
    """Calculate padding needed to align to 4-byte boundary."""
    remainder = offset % 4
    return 0 if remainder == 0 else 4 - remainder


def extract_cpio_files(
    archive_path: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    filter_files: Optional[List[str]] = None
) -> Optional[Dict[str, bytes]]:
    """
    Extract files from a CPIO archive (SWU file).

    Args:
        archive_path: Path to the .swu (CPIO) file
        output_dir: Directory to extract files to (for full extraction)
        filter_files: List of specific filenames to extract (selective extraction)

    Returns:
        If filter_files is provided: dict mapping filename -> file data (bytes)
        If output_dir is provided: None (files written to disk)

    Raises:
        ValueError: If invalid CPIO format
        FileNotFoundError: If archive doesn't exist
    """
    archive_path = Path(archive_path)
    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    with open(archive_path, 'rb') as f:
        archive_data = f.read()

    offset = 0
    extracted = {} if filter_files else None

    while offset < len(archive_data):
        if offset + 110 > len(archive_data):
            break

        header_bytes = archive_data[offset:offset + 110]
        offset += 110

        try:
            header = _parse_cpio_header(header_bytes)
        except ValueError:
            break

        namesize = header['namesize']
        if offset + namesize > len(archive_data):
            break

        filename_bytes = archive_data[offset:offset + namesize]
        offset += namesize

        offset += _align_to_4(offset)

        filename = filename_bytes.rstrip(b'\x00').decode('utf-8')

        if filename == 'TRAILER!!!':
            break

        filesize = header['filesize']
        if offset + filesize > len(archive_data):
            break

        file_data = archive_data[offset:offset + filesize]
        offset += filesize

        offset += _align_to_4(offset)

        mode = header['mode']
        is_dir = stat.S_ISDIR(mode)
        is_symlink = stat.S_ISLNK(mode)
        is_regular = stat.S_ISREG(mode)

        if filter_files is not None:
            if filename in filter_files:
                extracted[filename] = file_data
                if len(extracted) == len(filter_files):
                    return extracted

        elif output_dir is not None:
            output_path = Path(output_dir) / filename

            if is_dir:
                output_path.mkdir(parents=True, exist_ok=True)
            elif is_symlink:
                link_target = file_data.decode('utf-8')
                output_path.parent.mkdir(parents=True, exist_ok=True)
                if output_path.exists() or output_path.is_symlink():
                    output_path.unlink()
                output_path.symlink_to(link_target)
            elif is_regular:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'wb') as out_f:
                    out_f.write(file_data)
                os.chmod(output_path, mode & 0o777)

    if filter_files is not None:
        return extracted
    return None
