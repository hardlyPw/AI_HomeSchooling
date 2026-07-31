from __future__ import annotations

import base64
import hashlib
import os
import tempfile


class TempImageStorage:
    def decode_base64_image(self, image_b64: str) -> bytes:
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]
        return base64.b64decode(image_b64)

    def cache_key(self, image_bytes: bytes) -> str:
        return hashlib.sha256(image_bytes).hexdigest()

    def write_png(self, image_bytes: bytes) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        try:
            tmp.write(image_bytes)
            return tmp.name
        finally:
            tmp.close()

    def delete_if_exists(self, path: str | None) -> None:
        if path and os.path.isfile(path):
            try:
                os.unlink(path)
            except OSError:
                pass
