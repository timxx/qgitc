import os
import unittest

from qgitc.common import extractFilePaths, isRevisionRange, pathsEqual


class TestCommon(unittest.TestCase):
    def testIsRevisionRange(self):
        test_cases = [
            ("origin/master", True),
            ("HEAD~1", True),
            ("HEAD", True),
            ("master..feature", True),
            ("feature^", True),
            ("feature~2", True),
            ("a1b2c3d4", True),
            ("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0", True),
            ("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0a", False),
            ("feature", False),
            ("main", False),
            ("", False),
            ("1234", True),
            ("abcd", True),
            ("refs/heads/master", True),
            ("--since", False),
        ]
        for arg, expected in test_cases:
            with self.subTest(arg=arg):
                self.assertEqual(isRevisionRange(arg), expected)

    def testExtractFilePaths(self):
        test_cases = [
            ([], []),
            (["file1.txt"], ["file1.txt"]),
            (["--since", "yesterday", "file1.txt"], ["file1.txt"]),
            (["origin/master", "file1.txt"], ["file1.txt"]),
            (["file1.txt", "file2.txt"], ["file1.txt", "file2.txt"]),
            (["feature..main", "src/foo.py", "src/bar.py"],
             ["src/foo.py", "src/bar.py"]),
            (["--author", "bob", "src/foo.py"], ["src/foo.py"]),
            (["--author", "bob", "--since", "yesterday", "src/foo.py"], ["src/foo.py"]),
            (["--since", "yesterday"], []),
            (["--since", "yesterday", "--author", "bob"], []),
            (["HEAD~1", "src/foo.py"], ["src/foo.py"]),
            (["--max-count", "10", "src/foo.py"], ["src/foo.py"]),
            (["--max-count=10", "src/foo.py"], ["src/foo.py"]),
            (["--skip", "5", "src/foo.py"], ["src/foo.py"]),
            (["refs/heads/main", "docs/readme.md"], ["docs/readme.md"]),
            (["--format", "%h %s", "src/foo.py"], ["src/foo.py"]),
            (["--format=%h %s", "src/foo.py"], ["src/foo.py"]),
            (["--decorate-refs", "refs/heads/main", "src/foo.py"], ["src/foo.py"]),
            (["--decorate-refs=refs/heads/main", "src/foo.py"], ["src/foo.py"]),
            (["--not-an-arg", "src/foo.py"], ["src/foo.py"]),
            (["src/foo.py", "--since"], []),
            (["src/foo.py", "HEAD"], ["src/foo.py"]),
            (["src/foo.py", "HEAD", "--since"], []),
        ]

        for args, expected in test_cases:
            with self.subTest(args=args):
                self.assertEqual(extractFilePaths(args), expected)

    def testPathsEqual(self):
        """Test pathsEqual handles case-insensitivity and path separators correctly"""
        test_cases = [
            # Same paths
            ("/path/to/file.txt", "/path/to/file.txt", True),
            ("path/to/file.txt", "path/to/file.txt", True),

            # Different paths
            ("/path/to/file1.txt", "/path/to/file2.txt", False),
            ("path/to/file.txt", "other/file.txt", False),

            # Case sensitivity (should be equal on Windows, platform-dependent on Unix)
            ("C:/Path/To/File.txt", "c:/path/to/file.txt",
             os.name == "nt"),  # Equal on Windows
            ("/Path/To/File.txt", "/path/to/file.txt",
             os.name == "nt"),  # Equal on Windows, not on Unix

            # Path separator normalization (Windows: both / and \ should be treated the same)
            ("C:\\Path\\To\\File.txt", "C:/Path/To/File.txt", os.name == "nt"),
            ("path\\to\\file.txt", "path/to/file.txt", os.name == "nt"),

            # Combined: case + separator (Windows)
            ("C:\\Users\\Test\\file.txt", "c:/users/test/file.txt",
             os.name == "nt"),

            # None and empty string handling
            (None, None, True),
            ("", "", True),
            (None, "", False),
            ("", None, False),
            (None, "path", False),
            ("path", None, False),

            # Relative vs absolute (should be different)
            ("file.txt", "/path/to/file.txt", False),

            # Redundant separators and dots
            ("path//to/./file.txt", "path/to/file.txt", True),
            ("path/to/../to/file.txt", "path/to/file.txt", True),
        ]

        for path1, path2, expected in test_cases:
            with self.subTest(path1=path1, path2=path2):
                self.assertEqual(pathsEqual(path1, path2), expected,
                                 f"pathsEqual({path1!r}, {path2!r}) should be {expected}")
