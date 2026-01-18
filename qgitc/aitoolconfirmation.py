# -*- coding: utf-8 -*-

import json

from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QFontMetrics,
    QPainter,
    QPyTextObject,
    QTextDocument,
    QTextFormat,
)
from PySide6.QtWidgets import QApplication

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
                 tool_type: int = ToolType.READ_ONLY):
        self.tool_name = tool_name
        self.params = params
        self.tool_desc = tool_desc
        self.tool_type = tool_type
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
        self.minCardWidth = 350

        # Extra vertical spacing before action buttons (pending state)
        self.pendingButtonsTopSpacing = 6

        # Button dimensions for hit testing
        self.buttonWidth = 72
        self.buttonHeight = 24
        self.buttonSpacing = 8
        self.buttonStartMargin = 0

    def intrinsicSize(self, doc: QTextDocument, posInDocument, format: QTextFormat):
        """Return the size of the confirmation card"""
        width = self.minCardWidth
        data: ToolConfirmationData = format.property(QTextFormat.UserProperty)

        # Compute height dynamically since params can vary widely.
        # Layout (inside padded rect):
        #   description (optional, wrapped)
        #   params (optional, wrapped)
        #   status (only when NOT pending)
        #   buttons (only when pending)
        height = 0
        padding = self.cardPadding

        # Base: padding top/bottom
        height += padding * 2

        fm = QApplication.fontMetrics()
        lineHeight = fm.height()

        if data.tool_desc:
            height += lineHeight
            height += self.innerSpacing

        paramsText = self._formatParamsText(data.params)
        if paramsText:
            height += lineHeight
            height += self.innerSpacing

        if data.status == ConfirmationStatus.PENDING:
            height += self.pendingButtonsTopSpacing
            height += self.buttonHeight
        else:
            height += self.statusHeight

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

        # Draw description (single line, elided)
        font.setBold(False)
        painter.setFont(font)
        if data.tool_desc:
            descLine = fm.elidedText(data.tool_desc.replace(
                "\n", " "), Qt.ElideRight, textWidth)
            descRect = QRectF(innerRect.left(), y,
                              innerRect.width(), fm.height())
            painter.drawText(descRect, Qt.AlignLeft | Qt.AlignTop, descLine)
            y = descRect.bottom() + self.innerSpacing

        # Draw params (single line, elided)
        paramsText = self._formatParamsText(data.params)
        if paramsText:
            paramsLine = fm.elidedText(paramsText, Qt.ElideRight, textWidth)
            paramsRect = QRectF(innerRect.left(), y,
                                innerRect.width(), fm.height())
            painter.drawText(paramsRect, Qt.AlignLeft |
                             Qt.AlignTop, paramsLine)
            y = paramsRect.bottom() + self.innerSpacing

        if data.status == ConfirmationStatus.PENDING:
            self._drawButtons(painter, rect, data)
        else:
            schema: ColorSchema = ApplicationBase.instance().colorSchema()
            if data.status == ConfirmationStatus.APPROVED:
                painter.setPen(schema.ApproveText)
                statusText = self.tr("✓ Approved, executing...")
            else:
                painter.setPen(schema.RejectText)
                statusText = self.tr("✗ Rejected")

            statusRect = QRectF(innerRect.left(), y,
                                innerRect.width(), self.statusHeight)
            painter.drawText(statusRect, Qt.AlignLeft |
                             Qt.AlignTop, statusText)

        painter.restore()

    def _formatParamsText(self, params: dict) -> str:
        """Format tool params for display inside the confirmation card."""
        if not params:
            return ""

        try:
            # One-line JSON. Any newlines are normalized to spaces.
            formatted = json.dumps(
                params, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        except Exception:
            formatted = str(params)

        formatted = " ".join(str(formatted).splitlines())
        return self.tr("Arguments: {0}").format(formatted)

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
        buttonY = rect.bottom() - padding - self.buttonHeight
        startX = rect.left() + padding + self.buttonStartMargin

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
