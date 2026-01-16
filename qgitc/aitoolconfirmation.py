# -*- coding: utf-8 -*-

from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import QPainter, QPyTextObject, QTextDocument, QTextFormat
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
        # Button dimensions for hit testing
        self.buttonWidth = 80
        self.buttonHeight = 28
        self.buttonSpacing = 8

    def intrinsicSize(self, doc: QTextDocument, posInDocument, format: QTextFormat):
        """Return the size of the confirmation card"""
        # Fixed width based on document width, height based on content
        width = doc.textWidth() - 40  # Leave margins
        if width < 300:
            width = 300

        # Get status from format to adjust height
        data: ToolConfirmationData = format.property(QTextFormat.UserProperty)
        if data and data.status != ConfirmationStatus.PENDING:
            # Height without buttons: icon+title(30) + desc(20) + status(20) + padding(24)
            height = 94
        else:
            # Height with buttons: icon+title(30) + desc(20) + status(20) + spacing(15) + buttons(28) + padding(24)
            height = 137

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
        painter.drawRoundedRect(rect, 6, 6)

        # Calculate layout areas within the card
        padding = 12
        innerRect = rect.adjusted(padding, padding, -padding, -padding)

        # Set text color
        textColor = QApplication.palette().windowText().color()
        painter.setPen(textColor)

        # Draw icon and tool name
        icon = self._getIcon(data.tool_type)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        titleRect = QRectF(innerRect.left(), innerRect.top(),
                           innerRect.width(), 25)
        tips = self.tr("{0} AI wants to execute: {1}").format(
            icon, data.tool_name)
        painter.drawText(titleRect, Qt.AlignLeft | Qt.AlignTop, tips)

        # Draw description
        font.setBold(False)
        painter.setFont(font)
        if data.tool_desc:
            descRect = QRectF(innerRect.left(),
                              innerRect.top() + 30, innerRect.width(), 20)
            painter.drawText(descRect, Qt.AlignLeft | Qt.AlignTop,
                             data.tool_desc)

        # Draw status text
        schema: ColorSchema = ApplicationBase.instance().colorSchema()
        if data.status == ConfirmationStatus.APPROVED:
            painter.setPen(schema.ApproveText)
            statusText = self.tr("✓ Approved, executing...")
        elif data.status == ConfirmationStatus.REJECTED:
            painter.setPen(schema.RejectText)
            statusText = self.tr("✗ Rejected")
        else:
            painter.setPen(schema.WaitingText)
            statusText = self.tr("⏳ Waiting for your decision...")

        statusRect = QRectF(
            innerRect.left(), innerRect.top() + 55, innerRect.width(), 20)
        painter.drawText(statusRect, Qt.AlignLeft | Qt.AlignTop,
                         statusText)

        # Draw buttons only if pending
        if data.status == ConfirmationStatus.PENDING:
            self._drawButtons(painter, rect, data)

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
        padding = 12
        buttonY = rect.bottom() - padding - self.buttonHeight

        totalButtonWidth = self.buttonWidth * 2 + self.buttonSpacing
        startX = rect.left() + (rect.width() - totalButtonWidth) / 2

        approveRect = QRectF(
            startX, buttonY, self.buttonWidth, self.buttonHeight)
        rejectRect = QRectF(startX + self.buttonWidth + self.buttonSpacing,
                            buttonY, self.buttonWidth, self.buttonHeight)

        return approveRect, rejectRect

    def _getIcon(self, tool_type: int) -> str:
        """Get emoji icon based on tool type"""
        if tool_type == ToolType.READ_ONLY:
            return "🔍"
        elif tool_type == ToolType.WRITE:
            return "✏️"
        else:  # DANGEROUS
            return "⚠️"

    def _getColors(self, tool_type: int, hover=False):
        """Get background and border colors based on tool type"""
        schema: ColorSchema = ApplicationBase.instance().colorSchema()
        if tool_type == ToolType.READ_ONLY:
            return schema.ToolReadOnlyBg, schema.ToolReadOnlyHoverBorder if hover else schema.ToolReadOnlyBorder
        elif tool_type == ToolType.WRITE:
            return schema.ToolWriteBg, schema.ToolWriteHoverBorder if hover else schema.ToolWriteBorder
        else:  # DANGEROUS
            return schema.ToolDangerousBg, schema.ToolDangerousHoverBorder if hover else schema.ToolDangerousBorder
