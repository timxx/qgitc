# -*- coding: utf-8 -*-

import os
from unittest import skipIf

from qgitc.agenttoolexecutor import AgentToolExecutor
from qgitc.gitutils import Git
from tests.base import TestBase


class TestApplyPatchTool(TestBase):
    def test_apply_patch_updates_file(self):
        path = os.path.join(Git.REPO_DIR, "apply_patch_test.txt")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("line1\nline2\nline3\nold_line\nline5\nline6\nline7\n")

        patch_path = path.replace("\\", "/")
        patch = (
            "*** Begin Patch\n"
            f"*** Update File: {patch_path}\n"
            "line1\n"
            "line2\n"
            "line3\n"
            "-old_line\n"
            "+new_line\n"
            "line5\n"
            "line6\n"
            "line7\n"
            "*** End Patch\n"
        )

        executor = AgentToolExecutor()
        result = executor._handle_apply_patch(
            "apply_patch",
            {
                "input": patch,
                "explanation": "Replace old_line with new_line",
            },
        )

        self.assertTrue(result.ok, msg=result.output)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("new_line\n", content)
        self.assertNotIn("old_line\n", content)

    def test_apply_patch_rejects_outside_repo(self):
        outside = os.path.abspath(os.path.join(
            Git.REPO_DIR, os.pardir, "outside.txt"))
        outside_path = outside.replace("\\", "/")

        patch = (
            "*** Begin Patch\n"
            f"*** Update File: {outside_path}\n"
            "-x\n"
            "+y\n"
            "*** End Patch\n"
        )

        executor = AgentToolExecutor()
        result = executor._handle_apply_patch(
            "apply_patch",
            {
                "input": patch,
                "explanation": "Attempt to modify outside repo",
            },
        )

        self.assertFalse(result.ok)
        self.assertTrue(
            "outside" in result.output.lower() or "refusing" in result.output.lower(
            ) or "invalid" in result.output.lower(),
            msg=result.output,
        )

    def test_updates_real_case(self):
        path: str = os.path.join(Git.REPO_DIR, "test.py")
        patch_path = path.replace("\\", "/")

        patch = (
            "*** Begin Patch\n"
            f"*** Update File: {patch_path}\n"
            "@@\n"
            "     def _getConfirmDataAtPosition(self, pos: QPoint):\n"
            "         # get the block at the mouse position\n"
            "         button = ButtonType.NONE\n"
            "@@\n"
            "-        layout = block.layout()\n"
            "-        br = self.blockBoundingGeometry(block)\n"
            "+        layout = block.layout()\n"
            "+        br = self.blockBoundingGeometry(block).translated(self.contentOffset())\n"
            "         line = layout.lineForTextPosition(0)\n"
            "         if not line.isValid():\n"
            "             return None, button\n"
            "@@\n"
            "         lineRect = line.rect()\n"
            "         objRect = QRectF(\n"
            "             br.x() + lineRect.x(),\n"
            "             br.y() + lineRect.y(),\n             objSize.width(),\n"
            "             objSize.height()\n         )\n \n"
            "         # Check if mouse is within this confirmation's rectangle\n"
            "-        if not objRect.contains(pos):\n"
            "+        if not objRect.contains(QPointF(pos)):\n"
            "             return None, button\n"
            "@@\n"
            "             approveRect, rejectRect = self._toolConfirmInterface.getButtonRects(\n"
            "                 objRect)\n"
            "-            if approveRect.contains(pos):\n"
            "+            if approveRect.contains(QPointF(pos)):\n"
            "                 button = ButtonType.APPROVE\n"
            "-            elif rejectRect.contains(pos):\n"
            "+            elif rejectRect.contains(QPointF(pos)):\n"
            "                 button = ButtonType.REJECT\n \n"
            "         return confirmData, button\n"
            "*** End Patch"
        )

        old_content = """
    def _getConfirmDataAtPosition(self, pos: QPoint):
        # get the block at the mouse position
        button = ButtonType.NONE

        cursor = self.cursorForPosition(pos)
        block = cursor.block()
        if not block.isValid() or block.length() != 2 or not block.isVisible():
            return None, button

        confirmData = self._confirmations.get(block.position())
        if not confirmData:
            return None, button

        layout = block.layout()
        br = self.blockBoundingGeometry(block)
        line = layout.lineForTextPosition(0)
        if not line.isValid():
            return None, button

        cursor.setPosition(block.position())
        charFormat = cursor.charFormat()
        objSize = self._toolConfirmInterface.intrinsicSize(
            self.document(), pos, charFormat)
        lineRect = line.rect()
        objRect = QRectF(
            br.x() + lineRect.x(),
            br.y() + lineRect.y(),
            objSize.width(),
            objSize.height()
        )

        # Check if mouse is within this confirmation's rectangle
        if not objRect.contains(pos):
            return None, button

        if confirmData.status == ConfirmationStatus.PENDING:
            approveRect, rejectRect = self._toolConfirmInterface.getButtonRects(
                objRect)
            if approveRect.contains(pos):
                button = ButtonType.APPROVE
            elif rejectRect.contains(pos):
                button = ButtonType.REJECT

        return confirmData, button
"""

        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(old_content)

        executor = AgentToolExecutor()
        result = executor._handle_apply_patch(
            "apply_patch",
            {
                "input": patch,
                "explanation": "Fix bug",
            },
        )

        self.assertTrue(result.ok, msg=result.output)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(
            "br = self.blockBoundingGeometry(block).translated(self.contentOffset())\n", content)
        self.assertNotIn("br = self.blockBoundingGeometry(block)\n", content)

        self.assertIn(
            "        if not objRect.contains(QPointF(pos)):\n", content)
        self.assertNotIn("        if not objRect.contains(pos):\n", content)

        self.assertIn(
            "            if approveRect.contains(QPointF(pos)):\n", content)
        self.assertNotIn(
            "            if approveRect.contains(pos):\n", content)

        self.assertIn(
            "            elif rejectRect.contains(QPointF(pos)):\n", content)
        self.assertNotIn(
            "            elif rejectRect.contains(pos):\n", content)

    @skipIf(os.name != 'nt', "Unix-style path test only relevant on Windows")
    def test_apply_unix_path(self):
        path = os.path.join(Git.REPO_DIR, "sample.txt")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("hello")

        patch = """*** Begin Patch
*** Update File: /{}
-hello
*** End Patch""".format(path.replace("\\", "/").upper())

        path = path.replace("\\", "/")
        executor = AgentToolExecutor()
        result = executor._handle_apply_patch("apply_patch", {
            "input": patch,
            "explanation": "Fix bug",
        })
        self.assertTrue(result.ok, msg=result.output)
