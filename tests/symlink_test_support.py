from __future__ import annotations

import errno
import unittest
from pathlib import Path
from typing import Union


_SYMLINK_UNAVAILABLE_ERRNOS = {
    errno.EACCES,
    errno.EPERM,
    errno.ENOSYS,
    getattr(errno, "ENOTSUP", -1),
    getattr(errno, "EOPNOTSUPP", -1),
}
_WINDOWS_SYMLINK_PRIVILEGE_NOT_HELD = 1314


def symlink_or_skip(
    test_case: unittest.TestCase,
    link: Path,
    target: Union[str, Path],
    *,
    target_is_directory: bool = False,
) -> None:
    """Create a test symlink or skip only when the platform cannot do so."""

    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except NotImplementedError as exc:
        test_case.skipTest(f"symlinks unavailable: {exc}")
    except OSError as exc:
        if (
            getattr(exc, "winerror", None) == _WINDOWS_SYMLINK_PRIVILEGE_NOT_HELD
            or exc.errno in _SYMLINK_UNAVAILABLE_ERRNOS
        ):
            test_case.skipTest(f"symlinks unavailable: {exc}")
            return
        raise
