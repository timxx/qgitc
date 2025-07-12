import unittest

from qgitc.logsfetchergitworker import LogsFetcherGitWorker


class TestLogsFetcherGitWorker(unittest.TestCase):
    def test_isSupportFilterArgs_with_empty_list(self):
        self.assertTrue(LogsFetcherGitWorker.isSupportFilterArgs([]))
        self.assertTrue(LogsFetcherGitWorker.isSupportFilterArgs(None))

    def test_isSupportFilterArgs_with_supported_args(self):
        args = ["--since=1 week ago", "--author=John"]
        self.assertTrue(LogsFetcherGitWorker.isSupportFilterArgs(args))

    def test_isSupportFilterArgs_with_mixed_args(self):
        args = ["--since=2 days ago", "--max-count=10", "--author=Alice"]
        self.assertTrue(LogsFetcherGitWorker.isSupportFilterArgs(args))
        args.append("--grep=fix")
        self.assertFalse(LogsFetcherGitWorker.isSupportFilterArgs(args))

    def test_isSupportFilterArgs_with_all_unsupported(self):
        args = ["--grep=fix", "--max-count=5"]
        self.assertFalse(LogsFetcherGitWorker.isSupportFilterArgs(args))
