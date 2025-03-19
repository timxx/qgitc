# -*- coding: utf-8 -*-

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


__all__ = ["ColorSchema"]


class ColorSchema():

    Newline = QColor(0, 0, 255)
    Adding = QColor(0, 128, 0)
    Deletion = QColor(255, 0, 0)
    Modified = QColor(0xdbab09)
    Renamed = QColor(0x519143)
    RenamedModified = QColor(0x9a8246)
    Info = QColor(170, 170, 170)
    Whitespace = QColor(Qt.lightGray)
    SelFocus = QColor(173, 214, 255)
    SelNoFocus = QColor(229, 235, 241)
    Submodule = QColor(0, 160, 0)
    Submodule2 = QColor(255, 0, 0)
    FindResult = QColor(246, 185, 77)
    SimilarWord = QColor(226, 230, 214)
