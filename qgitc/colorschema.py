# -*- coding: utf-8 -*-

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


__all__ = ["ColorSchemaLight", "ColorSchemaDark", "ColorSchemaMode"]


class ColorSchemaMode:
    Auto = 0
    Light = 1
    Dark = 2


class ColorSchemaLight():

    Newline = QColor(0, 0, 255)
    Adding = QColor(0, 128, 0)
    Deletion = QColor(255, 0, 0)
    Modified = QColor(0xdbab09)
    Renamed = QColor(0x519143)
    RenamedModified = QColor(0x9a8246)
    InfoBg = QColor(0xE8F0FE)
    InfoFg = QColor(0x2B5070)
    InfoBorder = QColor(0xC0D0E0)
    Whitespace = QColor(Qt.lightGray)
    SelFocus = QColor(173, 214, 255)
    SelNoFocus = QColor(229, 235, 241)
    Submodule = QColor(0, 160, 0)
    Submodule2 = QColor(255, 0, 0)
    FindResult = QColor(246, 185, 77)
    SimilarWord = QColor(226, 230, 214)
    HighlightWordBg = QColor(0xFFF176)
    HighlightWordSelectedFg = Qt.yellow

    AuthorTagBg = QColor(232, 238, 244)
    AuthorTagFg = QColor(72, 94, 115)
    DateTagBg = QColor(234, 242, 237)
    DateTagFg = QColor(75, 104, 89)
    RepoTagBg = QColor(241, 238, 244)
    RepoTagFg = QColor(95, 82, 115)

    TagColorsBg = [
        Qt.yellow,
        Qt.green,
        QColor(255, 221, 170)
    ]
    TagColorsFg = [
        QColor(70, 55, 10),
        QColor(0, 60, 30),
        QColor(120, 50, 10)
    ]
    TagBorder = QColor(0, 100, 0)

    GraphColors = [
        Qt.black,
        Qt.red,
        Qt.green,
        Qt.blue,
        Qt.darkGray,
        QColor(150, 75, 0),  # brown
        Qt.magenta,
        QColor(255, 160, 50)  # orange
    ]
    GraphBorder = Qt.black

    LucColor = Qt.red
    LccColor = Qt.green

    Mark = QColor(0, 128, 0)
    ErrorText = QColor(240, 126, 116)

    HighlightLineBg = QColor(0xB3E0B3)

    # for list view
    SelectedItemBg = QColor(0x4DA3FF)
    SelectedItemFg = Qt.white
    HoverItemBg = SelNoFocus
    FocusItemBorder = QColor(0x0066CC)

    Splitter = Qt.darkGray
    LineNumber = Qt.darkGray


class ColorSchemaDark():

    Newline = QColor(100, 150, 255)
    Adding = QColor(76, 175, 80)
    Deletion = QColor(239, 83, 80)
    Modified = QColor(255, 213, 0)
    Renamed = QColor(106, 176, 76)
    RenamedModified = QColor(205, 149, 12)
    InfoBg = QColor(0x282C34)
    InfoFg = QColor(0xDDDDDD)
    InfoBorder = QColor(0x4B5363)
    Whitespace = QColor(68, 68, 68)
    SelFocus = QColor(42, 92, 117)
    SelNoFocus = QColor(58, 63, 69)
    Submodule = QColor(105, 240, 174)
    Submodule2 = QColor(255, 110, 64)
    FindResult = QColor(255, 153, 0)
    SimilarWord = QColor(69, 90, 100)
    HighlightWordBg = QColor(0x653306)
    HighlightWordSelectedFg = QColor(0xFFEB3B)

    AuthorTagBg = QColor(44, 62, 80)
    AuthorTagFg = QColor(158, 181, 202)
    DateTagBg = QColor(43, 61, 54)
    DateTagFg = QColor(143, 188, 159)
    RepoTagBg = QColor(54, 47, 72)
    RepoTagFg = QColor(175, 162, 194)

    TagColorsBg = [
        QColor(215, 191, 50),
        QColor(50, 100, 50),
        QColor(0xa46e0b)
    ]
    TagColorsFg = [
        QColor(40, 30, 0),
        QColor(220, 255, 220),
        QColor(0xdddddd)
    ]
    TagBorder = QColor(120, 80, 0)

    GraphColors = [
        QColor(200, 200, 200),
        QColor(220, 60, 60),
        QColor(0, 230, 118),
        QColor(70, 130, 255),
        QColor(160, 160, 160),
        QColor(165, 105, 0),
        QColor(200, 0, 200),
        QColor(255, 165, 0)
    ]
    GraphBorder = QColor(180, 180, 180)

    LucColor = QColor(255, 90, 90)
    LccColor = QColor(80, 230, 120)

    Mark = QColor(0, 230, 118)
    ErrorText = QColor(203, 80, 70)

    HighlightLineBg = QColor(0x1A4F49)

    # for list view
    SelectedItemBg = QColor(0x15385D)
    SelectedItemFg = QColor(0xFFFFFF)
    HoverItemBg = SelNoFocus
    FocusItemBorder = QColor(0x3377D2)

    Splitter = QColor(112, 112, 112)
    LineNumber = QColor(0x999999)
