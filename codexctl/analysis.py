import ext4
from remarkable_update_image import UpdateImage
from remarkable_update_image import UpdateImageSignatureException

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