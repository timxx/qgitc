import unittest

from qgitc.common import extractFilePaths, isRevisionRange


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
