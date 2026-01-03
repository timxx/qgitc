import os

from qgitc.gitutils import Git
from tests.base import TestBase


class TestGitUtils(TestBase):

    def createSubRepo(self):
        return True

    def testRestoreRepoFiles(self):
        # first renamed it to avoid `found` in subrepo
        process = Git.run(["mv", "README.md", "foo.md"])
        process.communicate()
        self.assertEqual(process.returncode, 0)

        Git.commit("Renamed README.md to foo.md")

        process = Git.run(["rm", "foo.md"])
        process.communicate()
        self.assertEqual(process.returncode, 0)

        os.chdir(os.path.join(self.gitDir.name, "subRepo"))

        repoFiles = {".": ["foo.md"]}
        error = Git.restoreRepoFiles(repoFiles, staged=True)
        self.assertIsNone(error)

    def testRawDiff(self):
        with open("test.dot", "w", encoding="utf-8") as f:
            pass
        with open("README.md", "a", encoding="utf-8") as f:
            f.write("# test")
        files = ["test.dot", "README.md"]
        self.assertIsNone(Git.addFiles(None, files))
        # git dosen't support *.dot, but we can still get the diff for README.md
        diff = Git.commitRawDiff(Git.LCC_SHA1, files)
        self.assertIsNotNone(diff)

        lines = diff.decode("utf-8").splitlines()
        self.assertIn("diff --git a/README.md b/README.md", lines)
        self.assertIn("+# test", lines)
        self.assertIn("diff --git a/test.dot b/test.dot", lines)

    def testRestoreFiles(self):
        """Test restoreFiles with newly added file - should not fail"""
        with open("newfile.txt", "w", encoding="utf-8") as f:
            f.write("test")
        self.assertIsNone(Git.addFiles(None, ["newfile.txt"]))

        # Should successfully unstage without error (newly added files won't be restored)
        error = Git.restoreFiles(None, ["newfile.txt"], staged=True)
        self.assertIsNone(error)

    def testRestoreStagedFilesNewlyAdded(self):
        """Test restoreStagedFiles with newly added file"""
        with open("newfile_staged.txt", "w", encoding="utf-8") as f:
            f.write("test content")
        self.assertIsNone(Git.addFiles(None, ["newfile_staged.txt"]))

        # restoreStagedFiles should successfully unstage without error
        error, filesToRestore = Git.restoreStagedFiles(
            None, ["newfile_staged.txt"])
        self.assertIsNone(error)
        # Newly added file should not be in filesToRestore (no unstaged changes)
        self.assertEqual(filesToRestore, [])

    def testRestoreStagedFilesModified(self):
        """Test restoreStagedFiles with modified file"""
        # First commit a file
        with open("existing.txt", "w", encoding="utf-8") as f:
            f.write("original content")
        self.assertIsNone(Git.addFiles(None, ["existing.txt"]))
        Git.commit("Add existing.txt")

        # Modify and stage it
        with open("existing.txt", "w", encoding="utf-8") as f:
            f.write("modified content")
        self.assertIsNone(Git.addFiles(None, ["existing.txt"]))

        # restoreStagedFiles should unstage and return it in filesToRestore
        error, filesToRestore = Git.restoreStagedFiles(None, ["existing.txt"])
        self.assertIsNone(error)
        # Modified file should be in filesToRestore (has unstaged changes after reset)
        self.assertIn("existing.txt", filesToRestore)

    def testRestoreFilesMixed(self):
        """Test restoreFiles with mix of newly added and modified files"""
        # Create and commit a file
        with open("committed.txt", "w", encoding="utf-8") as f:
            f.write("original")
        self.assertIsNone(Git.addFiles(None, ["committed.txt"]))
        Git.commit("Add committed.txt")

        # Modify the existing file
        with open("committed.txt", "w", encoding="utf-8") as f:
            f.write("modified")
        self.assertIsNone(Git.addFiles(None, ["committed.txt"]))

        # Add a new file
        with open("newfile_mixed.txt", "w", encoding="utf-8") as f:
            f.write("new content")
        self.assertIsNone(Git.addFiles(None, ["newfile_mixed.txt"]))

        # Restore both files - should not fail
        error = Git.restoreFiles(
            None, ["committed.txt", "newfile_mixed.txt"], staged=True)
        self.assertIsNone(error)

        # Check that the modified file was restored to original content
        with open("committed.txt", "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "original")

    def testChangeCommitAuthorHead(self):
        """Test changing the author of the HEAD commit"""
        # Get the HEAD commit SHA
        headSha = Git.revHead()
        self.assertIsNotNone(headSha)

        # Get the current branch
        branch = Git.activeBranch()
        self.assertIsNotNone(branch)

        # Change the author of HEAD commit
        newAuthor = "New Author"
        newEmail = "newauthor@test.com"
        ret, error = Git.changeCommitAuthor(
            branch, headSha, newAuthor, newEmail)

        # Check that the operation succeeded
        self.assertEqual(ret, 0, f"Failed to change author: {error}")

        # Verify the author was changed
        # After amending, the HEAD SHA changes, so get the new HEAD
        newHeadSha = Git.revHead()
        summary = Git.commitSummary(newHeadSha)
        self.assertIsNotNone(summary)
        self.assertEqual(summary["author"], newAuthor)
        self.assertEqual(summary["email"], newEmail)

    def testChangeCommitAuthorOlder(self):
        """Test changing the author of an older commit using rebase"""
        # Create a new commit so we have at least 2 commits
        with open("newfile2.txt", "w", encoding="utf-8") as f:
            f.write("new content")
        self.assertIsNone(Git.addFiles(None, ["newfile2.txt"]))
        Git.commit("Add newfile2")

        # Get the previous commit (not HEAD)
        process = Git.run(["rev-parse", "HEAD~1"])
        prevSha, _ = process.communicate()
        self.assertEqual(process.returncode, 0)
        prevSha = prevSha.decode("utf-8").strip()

        # Get the current branch
        branch = Git.activeBranch()
        self.assertIsNotNone(branch)

        # Change the author of the previous commit
        newAuthor = "Old Author Changed"
        newEmail = "oldchanged@test.com"
        ret, error = Git.changeCommitAuthor(
            branch, prevSha, newAuthor, newEmail)

        # Check that the operation succeeded
        self.assertEqual(ret, 0, f"Failed to change author: {error}")

        # Verify the author was changed
        summary = Git.commitSummary(prevSha)
        # Note: After rebase, the SHA might have changed, so we need to get the new SHA
        process = Git.run(["rev-parse", "HEAD~1"])
        newPrevSha, _ = process.communicate()
        newPrevSha = newPrevSha.decode("utf-8").strip()

        summary = Git.commitSummary(newPrevSha)
        self.assertIsNotNone(summary)
        self.assertEqual(summary["author"], newAuthor)
        self.assertEqual(summary["email"], newEmail)

    def testChangeCommitAuthorInvalidBranch(self):
        """Test changing author with invalid SHA"""
        branch = Git.activeBranch()
        invalidSha = "0000000000000000000000000000000000000000"
        ret, error = Git.changeCommitAuthor(
            branch, invalidSha, "Test", "test@test.com")

        # Should fail because the SHA doesn't exist
        self.assertNotEqual(ret, 0)

    def testRestoreStagedFilesSelectiveRestore(self):
        """Test that restoreStagedFiles only restores requested files, not all unstaged files.
        
        This tests the bug fix where restoreStagedFiles would incorrectly restore all files
        with unstaged changes instead of just the ones that were requested.
        
        Scenario:
        - Have two files: a.txt and b.txt, both with unstaged changes
        - Stage both files
        - Call restoreStagedFiles with only a.txt
        - Only a.txt should be returned in filesToRestore, not b.txt
        """
        # Create and commit two files
        with open("a.txt", "w", encoding="utf-8") as f:
            f.write("original a")
        with open("b.txt", "w", encoding="utf-8") as f:
            f.write("original b")
        self.assertIsNone(Git.addFiles(None, ["a.txt", "b.txt"]))
        Git.commit("Add a.txt and b.txt")

        # Modify both files
        with open("a.txt", "w", encoding="utf-8") as f:
            f.write("modified a")
        with open("b.txt", "w", encoding="utf-8") as f:
            f.write("modified b")

        # Stage both files
        self.assertIsNone(Git.addFiles(None, ["a.txt", "b.txt"]))

        # Now unstage only a.txt
        error, filesToRestore = Git.restoreStagedFiles(None, ["a.txt"])
        self.assertIsNone(error)

        # Only a.txt should be in filesToRestore, not b.txt
        self.assertIn("a.txt", filesToRestore)
        self.assertNotIn("b.txt", filesToRestore)
        self.assertEqual(len(filesToRestore), 1)
