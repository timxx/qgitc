import unittest
from unittest.mock import Mock

from qgitc.common import Commit
from qgitc.pickbranchwindow import PickBranchWindow


class TestPickBranchWindowRevertTracking(unittest.TestCase):
    """Test the revert tracking functionality in PickBranchWindow"""

    def setUp(self):
        """Create a mock PickBranchWindow for testing"""
        # Create a minimal instance without full UI setup
        self.window = PickBranchWindow.__new__(PickBranchWindow)

        # Mock the UI components we need
        self.window.ui = Mock()
        self.window.ui.logView = Mock()

    def _create_commit(self, sha1: str, message: str) -> Commit:
        """Helper to create a test commit"""
        commit = Commit(sha1=sha1, comments=message)
        return commit

    def _setup_commits(self, commits: list):
        """Setup mock logView with test commits"""
        self.window.ui.logView.getCount.return_value = len(commits)
        self.window.ui.logView.getCommit.side_effect = lambda idx: commits[idx] if 0 <= idx < len(
            commits) else None

    def test_single_revert(self):
        """Test filtering a single reverted commit"""
        commits = [
            self._create_commit(
                "abc1234", "Revert \"Fix bug\"\n\nThis reverts commit def4567."),
            self._create_commit("def4567", "Fix bug"),
        ]
        self._setup_commits(commits)

        reverted = self.window._buildRevertTrackingState()

        # def4567 should be marked as reverted
        # Note: The code matches the SHA from the message, so it must match exactly
        self.assertIn("def4567", reverted,
                      f"Expected def4567 in reverted set, got {reverted}")
        self.assertNotIn("abc1234", reverted)

    def test_reapply_commit(self):
        """Test that reapplied commits are not filtered"""
        commits = [
            self._create_commit(
                "xyz7890", "Reapply \"Fix bug\"\n\nThis reverts commit abc1234."),
            self._create_commit(
                "abc1234", "Revert \"Fix bug\"\n\nThis reverts commit def4567."),
            self._create_commit("def4567", "Fix bug"),
        ]
        self._setup_commits(commits)

        reverted = self.window._buildRevertTrackingState()

        # def4567 was reverted by abc1234, but then reapplied by xyz7890
        # So def4567 should NOT be in the reverted set
        self.assertNotIn("def4567", reverted)
        # abc1234 (the revert) was reverted by xyz7890 (reapply)
        self.assertIn("abc1234", reverted)

    def test_revert_of_reapply(self):
        """Test reverting a reapply (re-reverting)"""
        commits = [
            self._create_commit(
                "aaa0000", "Revert \"Reapply \"Fix bug\"\"\n\nThis reverts commit bbb1111."),
            self._create_commit(
                "bbb1111", "Reapply \"Fix bug\"\n\nThis reverts commit ccc2222."),
            self._create_commit(
                "ccc2222", "Revert \"Fix bug\"\n\nThis reverts commit ddd3333."),
            self._create_commit("ddd3333", "Fix bug"),
        ]
        self._setup_commits(commits)

        reverted = self.window._buildRevertTrackingState()

        # ddd3333 -> reverted by ccc2222 -> reapplied by bbb1111 -> re-reverted by aaa0000
        # Expected final state based on the toggle chain logic:
        # - ddd3333: should be reverted (toggled 3 times: False->True->False->True)
        # - ccc2222: should NOT be reverted (was reverted by bbb1111, then un-reverted by aaa0000)
        # - bbb1111: should be reverted (directly reverted by aaa0000)

        # But actually, let's think step by step:
        # 1. ccc2222 reverts ddd3333: ddd3333=reverted
        # 2. bbb1111 reverts ccc2222 (reapply): ddd3333=active, ccc2222=reverted
        # 3. aaa0000 reverts bbb1111: bbb1111=reverted, ccc2222=active, ddd3333=reverted

        self.assertIn("ddd3333", reverted,
                      f"ddd3333 should be reverted, got {reverted}")
        self.assertIn("bbb1111", reverted,
                      f"bbb1111 should be reverted, got {reverted}")
        self.assertNotIn("ccc2222", reverted,
                         f"ccc2222 should NOT be reverted, got {reverted}")

    def test_multiple_independent_reverts(self):
        """Test multiple independent revert operations"""
        commits = [
            self._create_commit(
                "aaabbb1", "Revert \"Feature A\"\n\nThis reverts commit cccdddd."),
            self._create_commit("cccdddd", "Feature A"),
            self._create_commit(
                "eeefff2", "Revert \"Feature B\"\n\nThis reverts commit abc9876."),
            self._create_commit("abc9876", "Feature B"),
        ]
        self._setup_commits(commits)

        reverted = self.window._buildRevertTrackingState()

        # Both features should be reverted
        self.assertIn("cccdddd", reverted)
        self.assertIn("abc9876", reverted)
        self.assertNotIn("aaabbb1", reverted)
        self.assertNotIn("eeefff2", reverted)

    def test_complex_revert_chain(self):
        """Test a complex chain of revert/reapply/re-revert"""
        commits = [
            self._create_commit(
                "eeeeeee", "Reapply \"Revert \"Reapply \"Fix bug\"\"\"\n\nThis reverts commit ddddddd."),
            self._create_commit(
                "ddddddd", "Revert \"Reapply \"Fix bug\"\"\n\nThis reverts commit ccccccc."),
            self._create_commit(
                "ccccccc", "Reapply \"Fix bug\"\n\nThis reverts commit bbbbbbb."),
            self._create_commit(
                "bbbbbbb", "Revert \"Fix bug\"\n\nThis reverts commit aaaaaaa."),
            self._create_commit("aaaaaaa", "Fix bug"),
        ]
        self._setup_commits(commits)

        reverted = self.window._buildRevertTrackingState()

        # aaaaaaa -> reverted by bbbbbbb (depth 1, reverted)
        # aaaaaaa -> reapplied by ccccccc (depth 1, active)
        # aaaaaaa -> re-reverted by ddddddd (depth 2, reverted)
        # aaaaaaa -> re-reapplied by eeeeeee (depth 3, active)
        # Final state: aaaaaaa should NOT be reverted (active)
        self.assertNotIn("aaaaaaa", reverted)

    def test_no_reverts(self):
        """Test when there are no revert commits"""
        commits = [
            self._create_commit("aaa", "Feature A"),
            self._create_commit("bbb", "Feature B"),
            self._create_commit("ccc", "Feature C"),
        ]
        self._setup_commits(commits)

        reverted = self.window._buildRevertTrackingState()

        # No commits should be reverted
        self.assertEqual(len(reverted), 0)

    def test_empty_commit_list(self):
        """Test with no commits"""
        self._setup_commits([])

        reverted = self.window._buildRevertTrackingState()

        self.assertEqual(len(reverted), 0)

    def test_calculate_revert_depth(self):
        """Test revert depth calculation"""
        # Depth 0: original commit
        depth = self.window._calculateRevertDepth("Fix bug")
        self.assertEqual(depth, 0)

        # Depth 1: revert
        depth = self.window._calculateRevertDepth("Revert \"Fix bug\"")
        self.assertEqual(depth, 1)

        # Depth 2: reapply (has both "Reapply" prefix and depth count)
        # Note: "Reapply" alone gives depth 1 because it counts as one nested level
        depth = self.window._calculateRevertDepth("Reapply \"Fix bug\"")
        self.assertEqual(depth, 1)

        # Depth 2: revert of reapply (2 nested levels)
        depth = self.window._calculateRevertDepth(
            "Revert \"Reapply \"Fix bug\"\"")
        self.assertEqual(depth, 2)

        # Depth 3: reapply of revert of reapply (3 nested levels)
        depth = self.window._calculateRevertDepth(
            "Reapply \"Revert \"Reapply \"Fix bug\"\"\"")
        self.assertEqual(depth, 3)

    def test_revert_with_matching_short_sha(self):
        """Test that short SHA matching works correctly"""
        commits = [
            self._create_commit(
                "rev", "Revert \"Feature\"\n\nThis reverts commit abc1234."),
            self._create_commit("abc1234567890", "Feature"),
        ]
        self._setup_commits(commits)

        reverted = self.window._buildRevertTrackingState()

        # Should match the short SHA
        self.assertIn("abc1234", reverted)

    def test_order_independence(self):
        """Test that processing order (oldest to newest) works correctly"""
        # Commits in chronological order (oldest first at bottom)
        commits = [
            self._create_commit(
                "abc1111", "Reapply \"Fix\"\n\nThis reverts commit def2222."),
            self._create_commit(
                "def2222", "Revert \"Fix\"\n\nThis reverts commit aaa3333."),
            self._create_commit("aaa3333", "Fix"),
        ]
        self._setup_commits(commits)

        reverted = self.window._buildRevertTrackingState()

        # aaa3333 was reverted then reapplied, should NOT be in reverted set
        self.assertNotIn("aaa3333", reverted)
        # def2222 (the revert) was itself reverted by abc1111
        self.assertIn("def2222", reverted)
