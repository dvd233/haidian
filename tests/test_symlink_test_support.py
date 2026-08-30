import errno
import unittest
from pathlib import Path
from unittest import mock

from tests.symlink_test_support import symlink_or_skip


class SymlinkTestSupportTests(unittest.TestCase):
    def test_creates_supported_symlink_without_skipping(self) -> None:
        test_case = mock.Mock(spec=unittest.TestCase)
        with mock.patch.object(Path, "symlink_to") as create_link:
            symlink_or_skip(
                test_case,
                Path("link"),
                Path("target"),
                target_is_directory=True,
            )

        create_link.assert_called_once_with(
            Path("target"), target_is_directory=True
        )
        test_case.skipTest.assert_not_called()

    def test_skips_when_symlinks_are_unavailable(self) -> None:
        for error in (
            NotImplementedError("unsupported"),
            OSError(errno.EPERM, "permission denied"),
        ):
            with self.subTest(error=type(error).__name__):
                test_case = mock.Mock(spec=unittest.TestCase)
                with mock.patch.object(Path, "symlink_to", side_effect=error):
                    symlink_or_skip(test_case, Path("link"), Path("target"))
                test_case.skipTest.assert_called_once()

    def test_reraises_unrelated_os_errors(self) -> None:
        test_case = mock.Mock(spec=unittest.TestCase)
        error = OSError(errno.ENOENT, "missing parent")
        with mock.patch.object(Path, "symlink_to", side_effect=error):
            with self.assertRaises(OSError) as caught:
                symlink_or_skip(test_case, Path("link"), Path("target"))

        self.assertIs(error, caught.exception)
        test_case.skipTest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
