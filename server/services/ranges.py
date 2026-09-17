"""HTTP byte-range parsing used by media streaming."""

import re

RANGE_WINDOW_BYTES = 8 * 1024 * 1024


def parse_single_range(value: str, file_size: int, window_bytes: int = RANGE_WINDOW_BYTES):
    """Parse one RFC 7233 byte range.

    Open-ended ranges are intentionally bounded to keep proxy responses small
    and reliable. Multipart ranges are not supported because browser playback
    does not require them.
    """
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or file_size <= 0:
        return None
    first, last = match.groups()
    if not first and not last:
        return None
    if len(first) > 20 or len(last) > 20:
        return None
    if not first:
        suffix = int(last)
        if suffix <= 0:
            return None
        return max(0, file_size - suffix), file_size - 1
    start = int(first)
    if start >= file_size:
        return None
    end = int(last) if last else min(start + window_bytes - 1, file_size - 1)
    if end < start:
        return None
    return start, min(end, file_size - 1)
