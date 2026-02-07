# -*- coding: utf-8 -*-

import os
import tempfile
import unittest
from pathlib import Path
from typing import List

from qgitc.gitutils import Git, GitProcess
from qgitc.tools.grepsearch import grepSearch


class TestGrepSearchTool(unittest.TestCase):

    def setUp(self):
        super().setUp()
        GitProcess.GIT_BIN = "git"

    def _git(self, repoDir: str, args: List[str]) -> None:
        process = Git.run(args, repoDir=repoDir, text=True)
        out, err = process.communicate()
        if process.returncode != 0:
            msg = err or ""
            raise AssertionError(f"git {' '.join(args)} failed: {msg}")

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

            self._git(repoDir, ["init"])
            Path(repoDir, ".gitignore").write_text(
                "ignored.txt\n", encoding="utf-8")

            Path(repoDir, "ignored.txt").write_text(
                "HELLO_IGNORED\n", encoding="utf-8")
            Path(repoDir, "tracked.txt").write_text(
                "HELLO_TRACKED\n", encoding="utf-8")

            self._git(repoDir, ["add", "tracked.txt"])

            result = grepSearch(
                repoDir=repoDir, query="HELLO_IGNORED", isRegexp=False)
            self.assertIn("No matches found.", result)
            self.assertNotIn("ignored.txt", result)

    def test_include_ignored_files_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            repoDir = str(Path(tmp))

            self._git(repoDir, ["init"])
            Path(repoDir, ".gitignore").write_text(
                "ignored.txt\n", encoding="utf-8")

            Path(repoDir, "ignored.txt").write_text(
                "HELLO_IGNORED\n", encoding="utf-8")
            Path(repoDir, "tracked.txt").write_text(
                "HELLO_TRACKED\n", encoding="utf-8")
            self._git(repoDir, ["add", "tracked.txt"])

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

            self._git(str(mainRepo), ["init"])
            self._git(str(mainRepo), [
                      "config", "user.email", "test@example.com"])
            self._git(str(mainRepo), ["config", "user.name", "Test"])

            (mainRepo / "README.md").write_text("base\n", encoding="utf-8")
            self._git(str(mainRepo), ["add", "README.md"])
            self._git(str(mainRepo), ["commit", "-m", "init"])

            self._git(str(mainRepo), ["worktree", "add", str(
                worktreeRepo), "-b", "feature"])

            self.assertTrue((worktreeRepo / ".git").is_file())

            (worktreeRepo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
            (worktreeRepo / "ignored.txt").write_text("HELLO_FROM_WORKTREE\n",
                                                      encoding="utf-8")
            (worktreeRepo / "tracked.txt").write_text("HELLO_TRACKED\n", encoding="utf-8")

            self._git(str(worktreeRepo), ["add", "tracked.txt"])

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
