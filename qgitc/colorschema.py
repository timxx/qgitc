# -*- coding: utf-8 -*-

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

__all__ = ["ColorSchemaLight", "ColorSchemaDark", "ColorSchemaMode"]


class ColorSchemaMode:
    Auto = 0
    Light = 1
    Dark = 2


class ColorSchema:
    Newline = QColor()
    Adding = QColor()
    Deletion = QColor()
    Modified = QColor()
    Renamed = QColor()
    RenamedModified = QColor()
    Untracked = QColor()
    Ignored = QColor()
    InfoBg = QColor()
    InfoFg = QColor()
    InfoBorder = QColor()
    Whitespace = QColor()
    SelFocus = QColor()
    SelNoFocus = QColor()
    Submodule = QColor()
    Submodule2 = QColor()
    FindResult = QColor()
    SimilarWord = QColor()
    HighlightWordBg = QColor()
    HighlightWordSelectedFg = QColor()

    AuthorTagBg = QColor()
    AuthorTagFg = QColor()
    DateTagBg = QColor()
    DateTagFg = QColor()
    RepoTagBg = QColor()
    RepoTagFg = QColor()
    TagColorsBg = []
    TagColorsFg = []
    TagBorder = QColor()
    GraphColors = []
    GraphBorder = QColor()
    LucColor = QColor()
    LccColor = QColor()
    Mark = QColor()
    ErrorText = QColor()
    HighlightLineBg = QColor()
    SelectedItemBg = QColor()
    SelectedItemFg = QColor()
    HoverItemBg = QColor()
    FocusItemBorder = QColor()
    Splitter = QColor()
    LineNumber = QColor()
    Comment = QColor()

    Heading = QColor()
    List = QColor()
    Bold = QColor()
    Keyword = QColor()
    String = QColor()
    Type = QColor()
    Other = QColor()
    Builtin = QColor()
    Literal = QColor()
    InlineCode = QColor()
    HorizontalRuler = QColor()

    UserBlockBorder = QColor()
    UserBlockBg = QColor()
    UserBlockFg = QColor()

    AssistantBlockBorder = QColor()
    AssistantBlockBg = QColor()
    AssistantBlockFg = QColor()

    SystemBlockBorder = QColor()
    SystemBlockBg = QColor()
    SystemBlockFg = QColor()


class ColorSchemaLight(ColorSchema):

    Newline = QColor(0, 0, 255)
    Adding = QColor(0, 128, 0)
    Deletion = QColor(255, 0, 0)
    Modified = QColor(0xdbab09)
    Renamed = QColor(0x519143)
    RenamedModified = QColor(0x9a8246)
    Untracked = QColor(0xd32f2f)
    Ignored = QColor(0x757575)
    InfoBg = QColor(0xE8F0FE)
    InfoFg = QColor(0x2B5070)
    InfoBorder = QColor(0xC0D0E0)
    Whitespace = QColor(Qt.lightGray)
    SelFocus = QColor(153, 201, 239)
    SelNoFocus = QColor(229, 235, 241)
    Submodule = QColor(0, 160, 0)
    Submodule2 = QColor(255, 0, 0)
    FindResult = QColor(246, 185, 77)
    SimilarWord = QColor(228, 216, 194)
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

    Comment = QColor(0x207f0b)

    Heading = QColor(0x1300a0)
    List = QColor(0x1300a0)
    Bold = List
    Keyword = QColor(0x3102fc)
    String = QColor(0x9c221b)
    Type = QColor(0x3a7e98)
    Other = QColor(0xab1ad9)
    Builtin = QColor(0x3a7e98)
    Literal = QColor(0x298559)
    InlineCode = QColor(0x7a1007)
    HorizontalRuler = QColor(0xc1c1c1)

    UserBlockBorder = QColor(0x1A73E8)
    UserBlockBg = QColor(0xE8F0FE)
    UserBlockFg = QColor(0x1A73E8)

    AssistantBlockBorder = QColor(0x0B8043)
    AssistantBlockBg = QColor(0xE8F5E9)
    AssistantBlockFg = QColor(0x0B8043)

    SystemBlockBorder = QColor(0x673AB7)
    SystemBlockBg = QColor(0xF3E8FD)
    SystemBlockFg = QColor(0x673AB7)


class ColorSchemaDark(ColorSchema):

    Newline = QColor(100, 150, 255)
    Adding = QColor(76, 175, 80)
    Deletion = QColor(239, 83, 80)
    Modified = QColor(255, 213, 0)
    Renamed = QColor(106, 176, 76)
    RenamedModified = QColor(205, 149, 12)
    Untracked = QColor(0xff5252)
    Ignored = QColor(0x9e9e9e)
    InfoBg = QColor(0x282C34)
    InfoFg = QColor(0xDDDDDD)
    InfoBorder = QColor(0x4B5363)
    Whitespace = QColor(100, 100, 100)
    SelFocus = QColor(11, 75, 115)
    SelNoFocus = QColor(58, 61, 65)
    Submodule = QColor(105, 240, 174)
    Submodule2 = QColor(255, 110, 64)
    FindResult = QColor(125, 78, 48)
    SimilarWord = QColor(77, 79, 81)
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

    Comment = QColor(0x6e9857)

    Heading = QColor(0x649bd5)
    List = QColor(0x649bd5)
    Bold = List
    Keyword = QColor(0x649bd5)
    String = QColor(0xc9856b)
    Type = QColor(0x62c7b0)
    Other = QColor(0xc188bf)
    Builtin = QColor(0x62c7b0)
    Literal = QColor(0xbdcda9)
    InlineCode = QColor(0xc9937a)
    HorizontalRuler = QColor(0x676767)

    UserBlockBorder = QColor(0x8AB4F8)
    UserBlockBg = QColor(0x1E3A5F)
    UserBlockFg = QColor(0x8AB4F8)

    AssistantBlockBorder = QColor(0x81C995)
    AssistantBlockBg = QColor(0x2C463D)
    AssistantBlockFg = QColor(0x81C995)

    SystemBlockBorder = QColor(0xB39DDB)
    SystemBlockBg = QColor(0x362B4F)
    SystemBlockFg = QColor(0xB39DDB)
