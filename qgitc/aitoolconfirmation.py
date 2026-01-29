# -*- coding: utf-8 -*-

from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QFontMetrics,
    QPainter,
    QPyTextObject,
    QTextDocument,
    QTextFormat,
)
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from qgitc.agenttools import ToolType
from qgitc.applicationbase import ApplicationBase
from qgitc.colorschema import ColorSchema


class ConfirmationStatus:
    """Status of tool confirmation"""
    PENDING = 0
    APPROVED = 1
    REJECTED = 2


class ButtonType:
    """Button type for hover tracking"""
    NONE = 0
    APPROVE = 1
    REJECT = 2


# Custom text object type ID for inline confirmations
TOOL_CONFIRMATION_OBJECT_TYPE = QTextFormat.UserObject + 1


class ToolConfirmationData:
    """
    Data structure for tool confirmation.
    Stored in QTextCharFormat as user property.
    """

    def __init__(self, tool_name: str, params: dict, tool_desc: str = None,
                 tool_type: int = ToolType.READ_ONLY, tool_call_id: str = None):
        self.tool_name = tool_name
        self.params = params
        self.tool_desc = tool_desc
        self.tool_type = tool_type
        # OpenAI tool_call_id (when available) so we can map tool results back
        # to the corresponding assistant tool call.
        self.tool_call_id = tool_call_id
        self.status = ConfirmationStatus.PENDING
        self.hovered = False  # Track hover state for entire card
        self.hovered_button = ButtonType.NONE  # Track which button is hovered


class ToolConfirmationInterface(QPyTextObject):
    """
    QTextObjectInterface implementation for rendering inline tool confirmations.
    
    This allows inserting tool confirmation cards directly into the QTextDocument
    using QChar.ObjectReplacementCharacter, and handles custom rendering and sizing.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Layout constants
        self.cardPadding = 8
        self.cardCornerRadius = 6
        self.innerSpacing = 4
        self.statusHeight = 20

        # Extra vertical spacing before action buttons (pending state)
        self.pendingButtonsTopSpacing = 6

        # Button dimensions for hit testing
        self.buttonWidth = 72
        self.buttonHeight = 24
        self.buttonSpacing = 8
        self.buttonStartMargin = 0

        # Minimum card width: fit at least a single button (vertical layout)
        self.minCardWidth = (
            self.cardPadding * 2
            + self.buttonStartMargin
            + self.buttonWidth
        )

    def _effectiveCardWidth(self):
        """Compute card width based on viewport and min width."""
        viewportWidth = self.viewportWidth()
        # Keep a little space so card doesn't flush to the viewport edge.
        available = max(0, viewportWidth - (self.cardPadding * 2))
        return max(self.minCardWidth, available)

    def _useVerticalButtons(self, cardRect: QRectF) -> bool:
        """Return True when buttons should be stacked vertically."""
        padding = self.cardPadding
        available = cardRect.width() - padding * 2 - self.buttonStartMargin
        neededHorizontal = (self.buttonWidth * 2) + self.buttonSpacing
        return available < neededHorizontal

    def _buttonBlockHeight(self, cardRect: QRectF) -> int:
        """Height needed for the buttons block in pending state."""
        if self._useVerticalButtons(cardRect):
            return (self.buttonHeight * 2) + self.buttonSpacing
        return self.buttonHeight

    def _wrappedTextHeight(self, fm: QFontMetrics, text: str, width: int) -> int:
        """Compute word-wrapped text height for a given width."""
        if not text:
            return 0
        # Use a very large height to let Qt compute wrapping.
        bounding = fm.boundingRect(
            0, 0, max(1, width), 10_000, Qt.TextWrapAnywhere, text)
        return bounding.height()

    def _statusTextForData(self, data: ToolConfirmationData) -> str:
        if data.status == ConfirmationStatus.APPROVED:
            return self.tr("✓ Approved, executing...")
        return self.tr("✗ Rejected")

    def viewportWidth(self):
        """Get the width of the viewport for layout purposes"""
        edit = self.parent()
        if isinstance(edit, QPlainTextEdit):
            return edit.viewport().width()
        return 0

    def intrinsicSize(self, doc: QTextDocument, posInDocument, format: QTextFormat):
        """Return the size of the confirmation card"""
        width = self._effectiveCardWidth()
        data: ToolConfirmationData = format.property(QTextFormat.UserProperty)

        height = 0
        padding = self.cardPadding

        # Base: padding top/bottom
        height += padding * 2

        edit = self.parent()
        if isinstance(edit, QPlainTextEdit):
            fm = edit.fontMetrics()
        else:
            fm = QFontMetrics(QApplication.font())

        if data.tool_desc:
            descText = data.tool_desc.splitlines()[0]
            textWidth = max(1, int(width - (padding * 2)))
            height += self._wrappedTextHeight(fm, descText, textWidth)
            height += self.innerSpacing

        if data.status == ConfirmationStatus.PENDING:
            height += self.pendingButtonsTopSpacing
            height += self._buttonBlockHeight(QRectF(0, 0, width, 1))
        else:
            textWidth = max(1, int(width - (padding * 2)))
            statusText = self._statusTextForData(data)
            height += max(self.statusHeight,
                          self._wrappedTextHeight(fm, statusText, textWidth))

        return QSizeF(width, height)

    def drawObject(self, painter: QPainter, rect: QRectF, doc, posInDocument, format: QTextFormat):
        """
        Draw the confirmation card.
        
        Args:
            painter: QPainter for drawing
            rect: Rectangle area to draw in
            doc: QTextDocument
            posInDocument: Position in document
            format: QTextCharFormat containing our custom data
        """
        # Get confirmation data from format
        data: ToolConfirmationData = format.property(QTextFormat.UserProperty)
        if not data:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw card background and border
        bgColor, borderColor = self._getColors(data.tool_type, data.hovered)
        painter.setPen(borderColor)
        painter.setBrush(bgColor)
        painter.drawRoundedRect(
            rect, self.cardCornerRadius, self.cardCornerRadius)

        # Calculate layout areas within the card
        padding = self.cardPadding
        innerRect = rect.adjusted(padding, padding, -padding, -padding)

        # Set text color
        textColor = QApplication.palette().windowText().color()
        painter.setPen(textColor)

        font = painter.font()
        y = innerRect.top()

        fm = painter.fontMetrics()
        textWidth = max(1, int(innerRect.width()))

        # Draw description (multi-line, word-wrapped)
        font.setBold(False)
        painter.setFont(font)
        if data.tool_desc:
            descText = data.tool_desc.splitlines()[0]
            descHeight = self._wrappedTextHeight(fm, descText, textWidth)
            descRect = QRectF(innerRect.left(), y,
                              innerRect.width(), descHeight)
            painter.drawText(descRect, Qt.AlignLeft |
                             Qt.AlignTop | Qt.TextWrapAnywhere, descText)
            y = descRect.bottom() + self.innerSpacing

        if data.status == ConfirmationStatus.PENDING:
            self._drawButtons(painter, rect, data)
        else:
            schema: ColorSchema = ApplicationBase.instance().colorSchema()
            if data.status == ConfirmationStatus.APPROVED:
                painter.setPen(schema.ApproveText)
                statusText = self._statusTextForData(data)
            else:
                painter.setPen(schema.RejectText)
                statusText = self._statusTextForData(data)

            statusHeight = max(self.statusHeight, self._wrappedTextHeight(
                fm, statusText, textWidth))
            statusRect = QRectF(innerRect.left(), y,
                                innerRect.width(), statusHeight)
            painter.drawText(statusRect, Qt.AlignLeft |
                             Qt.AlignTop | Qt.TextWrapAnywhere, statusText)

        painter.restore()

    def _drawButtons(self, painter: QPainter, rect: QRectF, data: ToolConfirmationData):
        """Draw approve and reject buttons"""
        approveRect, rejectRect = self.getButtonRects(rect)

        schema = ApplicationBase.instance().colorSchema()

        if data.hovered_button == ButtonType.APPROVE:
            approveColor = schema.ApproveButtonHoverBg
        else:
            approveColor = schema.ApproveButtonBg
        painter.setBrush(approveColor)
        painter.setPen(approveColor)
        painter.drawRoundedRect(approveRect, 4, 4)

        painter.setPen(Qt.white)
        painter.drawText(approveRect, Qt.AlignCenter, self.tr("Approve"))

        if data.hovered_button == ButtonType.REJECT:
            rejectColor = schema.RejectButtonHoverBg
        else:
            rejectColor = schema.RejectButtonBg
        painter.setBrush(rejectColor)
        painter.setPen(rejectColor)
        painter.drawRoundedRect(rejectRect, 4, 4)

        painter.setPen(Qt.white)
        painter.drawText(rejectRect, Qt.AlignCenter, self.tr("Reject"))

    def getButtonRects(self, rect: QRectF):
        """Calculate button rectangles for hit testing"""
        padding = self.cardPadding
        startX = rect.left() + padding + self.buttonStartMargin

        # Stack buttons vertically if the available width cannot fit both.
        if self._useVerticalButtons(rect):
            rejectY = rect.bottom() - padding - self.buttonHeight
            approveY = rejectY - self.buttonSpacing - self.buttonHeight
            approveRect = QRectF(
                startX, approveY, self.buttonWidth, self.buttonHeight)
            rejectRect = QRectF(
                startX, rejectY, self.buttonWidth, self.buttonHeight)
            return approveRect, rejectRect

        buttonY = rect.bottom() - padding - self.buttonHeight

        approveRect = QRectF(
            startX, buttonY, self.buttonWidth, self.buttonHeight)
        rejectRect = QRectF(startX + self.buttonWidth + self.buttonSpacing,
                            buttonY, self.buttonWidth, self.buttonHeight)

        return approveRect, rejectRect

    def _getColors(self, tool_type: int, hover=False):
        """Get background and border colors based on tool type"""
        schema: ColorSchema = ApplicationBase.instance().colorSchema()
        if tool_type == ToolType.READ_ONLY:
            return schema.ToolReadOnlyBg, schema.ToolReadOnlyHoverBorder if hover else schema.ToolReadOnlyBorder
        elif tool_type == ToolType.WRITE:
            return schema.ToolWriteBg, schema.ToolWriteHoverBorder if hover else schema.ToolWriteBorder
        else:  # DANGEROUS
            return schema.ToolDangerousBg, schema.ToolDangerousHoverBorder if hover else schema.ToolDangerousBorder
