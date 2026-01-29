# -*- coding: utf-8 -*-

import os
from unittest import skipIf

from qgitc.agenttoolexecutor import AgentToolExecutor
from qgitc.gitutils import Git
from tests.base import TestBase


class TestApplyPatchTool(TestBase):
    def _assert_only_crlf_bytes(self, data: bytes):
        # Ensure every LF byte is preceded by CR.
        for i, b in enumerate(data):
            if b == 0x0A:  # '\n'
                self.assertGreater(i, 0, msg="LF at start of file")
                self.assertEqual(data[i - 1], 0x0D,
                                 msg="Found lone LF (not CRLF)")

    def _assert_only_crlf_utf16le(self, data: bytes):
        # Ensure every UTF-16LE LF sequence (0A 00) is preceded by CR (0D 00).
        for i in range(0, len(data) - 1):
            if data[i] == 0x0A and data[i + 1] == 0x00:
                self.assertGreaterEqual(
                    i, 2, msg="UTF-16LE LF at start of file")
                self.assertEqual(data[i - 2], 0x0D,
                                 msg="Found lone UTF-16LE LF (not CRLF)")
                self.assertEqual(
                    data[i - 1], 0x00, msg="Found malformed UTF-16LE CR before LF")

    def test_apply_patch_updates_file(self):
        path = os.path.join(Git.REPO_DIR, "apply_patch_test.txt")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("line1\nline2\nline3\nold_line\nline5\nline6\nline7\n")

        patch_path = path.replace("\\", "/")
        patch = (
            "*** Begin Patch\n"
            f"*** Update File: {patch_path}\n"
            " line1\n"
            " line2\n"
            " line3\n"
            "-old_line\n"
            "+new_line\n"
            " line5\n"
            " line6\n"
            " line7\n"
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

    def test_apply_patch_preserves_crlf_newlines(self):
        path = os.path.join(Git.REPO_DIR, "apply_patch_crlf.txt")
        with open(path, "wb") as f:
            f.write(b"line1\r\nline2\r\nold_line\r\nline4\r\n")

        patch_path = path.replace("\\", "/")
        patch = (
            "*** Begin Patch\n"
            f"*** Update File: {patch_path}\n"
            " line1\n"
            " line2\n"
            "-old_line\n"
            "+new_line\n"
            " line4\n"
            "*** End Patch\n"
        )

        executor = AgentToolExecutor()
        result = executor._handle_apply_patch(
            "apply_patch",
            {
                "input": patch,
                "explanation": "Replace old_line with new_line (preserve CRLF)",
            },
        )

        self.assertTrue(result.ok, msg=result.output)
        with open(path, "rb") as f:
            data = f.read()
        self._assert_only_crlf_bytes(data)
        self.assertIn(b"new_line\r\n", data)
        self.assertNotIn(b"old_line\r\n", data)

    def test_apply_patch_preserves_utf16le_bom_and_crlf(self):
        path = os.path.join(Git.REPO_DIR, "apply_patch_utf16le.txt")
        # Write UTF-16LE with BOM and CRLF.
        text = "line1\r\nline2\r\nold_line\r\nline4\r\n"
        with open(path, "wb") as f:
            f.write(b"\xff\xfe")
            f.write(text.encode("utf-16-le"))

        patch_path = path.replace("\\", "/")
        patch = (
            "*** Begin Patch\n"
            f"*** Update File: {patch_path}\n"
            " line1\n"
            " line2\n"
            "-old_line\n"
            "+new_line\n"
            " line4\n"
            "*** End Patch\n"
        )

        executor = AgentToolExecutor()
        result = executor._handle_apply_patch(
            "apply_patch",
            {
                "input": patch,
                "explanation": "Replace old_line with new_line (preserve UTF-16LE BOM/CRLF)",
            },
        )

        self.assertTrue(result.ok, msg=result.output)
        with open(path, "rb") as f:
            data = f.read()

        self.assertTrue(data.startswith(b"\xff\xfe"),
                        msg="Missing UTF-16LE BOM")
        self._assert_only_crlf_utf16le(data[2:])
        # Verify content in bytes (UTF-16LE)
        self.assertIn("new_line\r\n".encode("utf-16-le"), data)
        self.assertNotIn("old_line\r\n".encode("utf-16-le"), data)

    def test_apply_patch_preserves_mixed_newlines_locally(self):
        # The file intentionally mixes LF and CRLF. The patch should preserve
        # newline style based on nearby original lines, not normalize the whole file.
        path = os.path.join(Git.REPO_DIR, "apply_patch_mixed_newlines.txt")
        original = (
            b"lf1\n"
            b"lf2\n"
            b"crlf1\r\n"
            b"old_line\r\n"
            b"crlf3\r\n"
            b"lf_tail\n"
        )
        with open(path, "wb") as f:
            f.write(original)

        patch_path = path.replace("\\", "/")
        patch = (
            "*** Begin Patch\n"
            f"*** Update File: {patch_path}\n"
            " lf1\n"
            " lf2\n"
            "+inserted_line\n"
            " crlf1\n"
            "-old_line\n"
            "+new_line\n"
            " crlf3\n"
            " lf_tail\n"
            "*** End Patch\n"
        )

        executor = AgentToolExecutor()
        result = executor._handle_apply_patch(
            "apply_patch",
            {
                "input": patch,
                "explanation": "Insert after LF and replace within CRLF block",
            },
        )

        self.assertTrue(result.ok, msg=result.output)
        with open(path, "rb") as f:
            data = f.read()

        # Inserted line should be LF (because it follows an LF line).
        pos = data.index(b"inserted_line")
        end = pos + len(b"inserted_line")
        self.assertEqual(data[end:end + 1], b"\n",
                         msg="inserted_line should end with LF")
        self.assertNotEqual(data[end - 1:end + 1], b"\r\n",
                            msg="inserted_line should not be CRLF")

        # Replaced line should be CRLF (because it replaced a CRLF line).
        pos = data.index(b"new_line")
        end = pos + len(b"new_line")
        self.assertEqual(data[end:end + 2], b"\r\n",
                         msg="new_line should end with CRLF")

        # Neighbor lines should remain as originally encoded.
        self.assertIn(b"crlf1\r\n", data)
        self.assertIn(b"crlf3\r\n", data)
        self.assertIn(b"lf_tail\n", data)

    def test_apply_patch_does_not_touch_indent_only_changes(self):
        # If the new content differs only by tab/space indentation,
        # the original line should be preserved exactly.
        path = os.path.join(Git.REPO_DIR, "apply_patch_indent_only.py")
        original = "\tvalue = 1\n"
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(original)

        patch = (
            "*** Begin Patch\n"
            f"*** Update File: {path}\n"
            "-\tvalue = 1\n"
            "+    value = 1\n"
            "*** End Patch\n"
        )

        executor = AgentToolExecutor()
        result = executor._handle_apply_patch(
            "apply_patch",
            {
                "input": patch,
                "explanation": "Indent-only change should not modify the line",
            },
        )

        self.assertTrue(result.ok, msg=result.output)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, original)

    def test_apply_patch_preserves_old_indent_char_on_replacement(self):
        # If a replacement line changes content but uses spaces where the original used tabs,
        # prefer the original indent character.
        path = os.path.join(Git.REPO_DIR, "apply_patch_indent_style.py")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\tprint('old')\n")

        patch = (
            "*** Begin Patch\n"
            f"*** Update File: {path}\n"
            "-\tprint('old')\n"
            "+    print('new')\n"
            "*** End Patch\n"
        )

        executor = AgentToolExecutor()
        result = executor._handle_apply_patch(
            "apply_patch",
            {
                "input": patch,
                "explanation": "Replacement should keep original indent char",
            },
        )

        self.assertTrue(result.ok, msg=result.output)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "\tprint('new')\n")

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

        executor = AgentToolExecutor()
        result = executor._handle_apply_patch("apply_patch", {
            "input": patch,
            "explanation": "Fix bug",
        })
        self.assertTrue(result.ok, msg=result.output)

    def test_anchors(self):
        path = os.path.join(Git.REPO_DIR, "test.cpp").replace("\\", "/")

        def _create_file():
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("""// comment
\tvoid foo()
{
#ifndef Q_OS_UNIX
\tint bar = 1;
#else
\tint bar = 2;
#endif
}

// another comment
""")

        # both `@@ void foo()` and `@@void foo()` should be accepted
        patch = """*** Begin Patch
*** Update File: {}
{}
-#ifndef Q_OS_UNIX
+#ifdef Q_OS_WIN
*** End Patch"""

        def _test(patch: str):
            executor = AgentToolExecutor()
            _create_file()
            result = executor._handle_apply_patch("apply_patch", {
                "input": patch,
                "explanation": "Fix bug",
            })
            self.assertTrue(result.ok, msg=result.output)

            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("#ifdef Q_OS_WIN", content)
            self.assertNotIn("#ifndef Q_OS_UNIX", content)

        _test(patch.format(path, "@@ void foo()"))
        _test(patch.format(path, "@@void foo()"))
