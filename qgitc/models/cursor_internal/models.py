# -*- coding: utf-8 -*-


from dataclasses import dataclass
from typing import Optional


@dataclass
class AvailableModel:
    id: Optional[str] = None
    name: Optional[str] = None
    displayName: Optional[str] = None
    defaultOn: bool = False
    isLongContextOnly: bool = False
    isChatOnly: bool = False
    supportsAgent: bool = False
    supportsThinking: bool = False
