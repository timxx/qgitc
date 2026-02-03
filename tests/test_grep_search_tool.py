# -*- coding: utf-8 -*-

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from qgitc.tools.grepsearch import grepSearch


class TestGrepSearchTool(unittest.TestCase):

    def _write(self, root: str, rel: str, content: bytes):
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(content)
        return path

    def test_plain_text_search_case_insensitive(self):
        with tempfile.TemporaryDirectory() as td:
            self._write(td, 'a.txt', b'Hello World\nnope\n')
            self._write(td, 'sub/b.txt', b'say hello again\n')

            out = grepSearch(repoDir=td, query='hello', isRegexp=False)
            self.assertIn('a.txt:1:', out)
            self.assertIn('sub/b.txt:1:', out)
            self.assertIn('Matches:', out)

    def test_regex_search(self):
        with tempfile.TemporaryDirectory() as td:
            self._write(td, 'a.txt', b'abc123\nABC999\nzzz\n')

            out = grepSearch(repoDir=td, query=r'abc\d+', isRegexp=True)
            # case-insensitive: matches both lines 1 and 2
            self.assertIn('a.txt:1:', out)
            self.assertIn('a.txt:2:', out)

    def test_include_pattern_limits_files(self):
        with tempfile.TemporaryDirectory() as td:
            self._write(td, 'a.txt', b'needle\n')
            self._write(td, 'b.md', b'needle\n')
            self._write(td, 'sub/c.txt', b'needle\n')

            out = grepSearch(
                repoDir=td,
                query='needle',
                isRegexp=False,
                includePattern='**/*.md',
            )
            self.assertIn('b.md:1:', out)
            self.assertNotIn('a.txt:1:', out)
            self.assertNotIn('sub/c.txt:1:', out)

    def test_max_results_truncates(self):
        with tempfile.TemporaryDirectory() as td:
            # 10 matching lines
            self._write(td, 'a.txt', b"".join([b'hit\n' for _ in range(10)]))

            out = grepSearch(repoDir=td, query='hit',
                             isRegexp=False, maxResults=3)
            # Expect only 3 match lines + a summary with truncation.
            self.assertIn('a.txt:1:', out)
            self.assertIn('a.txt:2:', out)
            self.assertIn('a.txt:3:', out)
            self.assertNotIn('a.txt:4:', out)
            self.assertIn('Truncated: true', out)

    def test_skips_binary_files(self):
        with tempfile.TemporaryDirectory() as td:
            self._write(td, 'bin.dat', b'hello\x00world\n')
            self._write(td, 'a.txt', b'hello\n')

            out = grepSearch(repoDir=td, query='hello', isRegexp=False)
            self.assertIn('a.txt:1:', out)
            self.assertNotIn('bin.dat', out)

    def test_respects_gitignore_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            repoDir = str(Path(tmp))

            subprocess.run(
                ["git", "init"],
                cwd=repoDir,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            Path(repoDir, ".gitignore").write_text(
                "ignored.txt\n", encoding="utf-8")

            Path(repoDir, "ignored.txt").write_text(
                "HELLO_IGNORED\n", encoding="utf-8")
            Path(repoDir, "tracked.txt").write_text(
                "HELLO_TRACKED\n", encoding="utf-8")

            subprocess.run(
                ["git", "add", "tracked.txt"],
                cwd=repoDir,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            result = grepSearch(
                repoDir=repoDir, query="HELLO_IGNORED", isRegexp=False)
            self.assertIn("No matches found.", result)
            self.assertNotIn("ignored.txt", result)

    def test_include_ignored_files_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            repoDir = str(Path(tmp))

            subprocess.run(
                ["git", "init"],
                cwd=repoDir,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            Path(repoDir, ".gitignore").write_text(
                "ignored.txt\n", encoding="utf-8")

            Path(repoDir, "ignored.txt").write_text(
                "HELLO_IGNORED\n", encoding="utf-8")
            Path(repoDir, "tracked.txt").write_text(
                "HELLO_TRACKED\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "tracked.txt"],
                cwd=repoDir,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            result = grepSearch(
                repoDir=repoDir,
                query="HELLO_IGNORED",
                isRegexp=False,
                includeIgnoredFiles=True,
            )
            self.assertIn("ignored.txt", result)

    def test_git_worktree_dotgit_is_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpPath = Path(tmp)
            mainRepo = tmpPath / "main"
            worktreeRepo = tmpPath / "worktree"
            mainRepo.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                ["git", "init"],
                cwd=str(mainRepo),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=str(mainRepo),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=str(mainRepo),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            (mainRepo / "README.md").write_text("base\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "README.md"],
                cwd=str(mainRepo),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=str(mainRepo),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            subprocess.run(
                ["git", "worktree", "add", str(worktreeRepo), "-b", "feature"],
                cwd=str(mainRepo),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertTrue((worktreeRepo / ".git").is_file())

            (worktreeRepo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
            (worktreeRepo / "ignored.txt").write_text("HELLO_FROM_WORKTREE\n",
                                                      encoding="utf-8")
            (worktreeRepo / "tracked.txt").write_text("HELLO_TRACKED\n", encoding="utf-8")

            subprocess.run(
                ["git", "add", "tracked.txt"],
                cwd=str(worktreeRepo),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            outDefault = grepSearch(
                repoDir=str(worktreeRepo),
                query="HELLO_FROM_WORKTREE",
                isRegexp=False,
            )
            self.assertIn("No matches found.", outDefault)
            self.assertNotIn("ignored.txt", outDefault)

            outInclude = grepSearch(
                repoDir=str(worktreeRepo),
                query="HELLO_FROM_WORKTREE",
                isRegexp=False,
                includeIgnoredFiles=True,
            )
            self.assertIn("ignored.txt", outInclude)
