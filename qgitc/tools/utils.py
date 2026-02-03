# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Optional, Tuple


def detectBom(path: str) -> Tuple[Optional[bytes], str]:
    """Return (bom_bytes, encoding_name_for_text) for common Unicode BOMs."""
    try:
        with open(path, 'rb') as fb:
            head = fb.read(4)
    except Exception:
        return None, 'utf-8'

    if head.startswith(b'\xff\xfe\x00\x00'):
        return b'\xff\xfe\x00\x00', 'utf-32-le'
    if head.startswith(b'\x00\x00\xfe\xff'):
        return b'\x00\x00\xfe\xff', 'utf-32-be'
    if head.startswith(b'\xff\xfe'):
        return b'\xff\xfe', 'utf-16-le'
    if head.startswith(b'\xfe\xff'):
        return b'\xfe\xff', 'utf-16-be'
    if head.startswith(b'\xef\xbb\xbf'):
        return b'\xef\xbb\xbf', 'utf-8-sig'

    return None, 'utf-8'
