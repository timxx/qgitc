# -*- coding: utf-8 -*-

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


__all__ = ["ColorSchemaLight", "ColorSchemaDark"]


class ColorSchemaLight():

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


class ColorSchemaDark():

    Newline = QColor(100, 150, 255)
    Adding = QColor(76, 175, 80)
    Deletion = QColor(239, 83, 80)
    Modified = QColor(255, 213, 0)
    Renamed = QColor(106, 176, 76)
    RenamedModified = QColor(205, 149, 12)
    Info = QColor(136, 136, 136)
    Whitespace = QColor(68, 68, 68)
    SelFocus = QColor(42, 92, 117)
    SelNoFocus = QColor(58, 63, 69)
    Submodule = QColor(105, 240, 174)
    Submodule2 = QColor(255, 110, 64)
    FindResult = QColor(255, 153, 0)
    SimilarWord = QColor(69, 90, 100)
