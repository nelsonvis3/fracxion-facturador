"""Private raster input validation shared by logos and expense attachments."""

import base64
import binascii
import warnings
from io import BytesIO

from PIL import Image, UnidentifiedImageError
from rest_framework import serializers


def decode_private_image(value, *, thumbnail=(512, 512), max_output=256 * 1024):
    try:
        content = base64.b64decode(value, validate=True)
        if len(content) > 512 * 1024:
            raise ValueError()
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content), formats=["PNG", "JPEG"]) as image:
                if (
                    not (1 <= image.width <= 2048 and 1 <= image.height <= 2048)
                    or image.width * image.height > 2_000_000
                ):
                    raise ValueError()
                image.load()
                image.thumbnail(thumbnail)
                clean = Image.new("RGBA", image.size)
                clean.paste(image.convert("RGBA"))
                output = BytesIO()
                clean.save(output, format="PNG", optimize=True)
                if len(output.getvalue()) > max_output:
                    raise ValueError()
                return output.getvalue()
    except (
        ValueError,
        TypeError,
        binascii.Error,
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise serializers.ValidationError(
            "Usá una imagen PNG o JPEG de hasta 512 KB y 2048 px por lado."
        )
