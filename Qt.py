"""Qt modules import wrapper

Base on https://github.com/mottosso/Qt.py
But only keep module import, no made any compatibility
"""

import os
import sys
import types


# Enable support for `from Qt import *`
__all__ = []

# Flags from environment variables
QT_VERBOSE = bool(os.getenv("QT_VERBOSE"))
QT_BINDING = os.getenv("QT_BINDING", "")

# Reference to Qt.py
Qt = sys.modules[__name__]

_qt_modules = [
    "QtCore",
    "QtGui",
    "QtWidgets",
    "uic",
]


def _import_sub_module(module, name):
    """import_sub_module will mimic the function of importlib.import_module"""
    module = __import__(module.__name__ + "." + name)
    for level in name.split("."):
        module = getattr(module, level)
    return module


def _enable_import(name, module):
    # Store reference to original binding
    setattr(Qt, name, module)

    # Enable import *
    __all__.append(name)

    # Enable direct import of submodule,
    # e.g. import Qt.QtCore
    sys.modules[__name__ + "." + name] = module


def _setup(module):
    for name in _qt_modules:
        try:
            submodule = _import_sub_module(
                module, name)
        except ImportError:
            continue

        _enable_import(name, submodule)


def _pyqt5():
    import PyQt5 as module
    _setup(module)


def _pyqt4():
    import PyQt4 as module
    _setup(module)

    if hasattr(Qt, "QtGui"):
        _enable_import("QtWidgets", Qt.QtGui)


def _install():
    default_order = ("PyQt5", "PyQt4")
    preferred_order = [QT_BINDING] if QT_BINDING else []

    order = preferred_order or default_order
    available = {
        "PyQt5": _pyqt5,
        "PyQt4": _pyqt4,
    }

    for name in order:
        _log("Trying %s" % name)
        try:
            available[name]()
            break
        except ImportError as e:
            _log("ImportError: %s" % e)
        except KeyError:
            _log("ImportError: Preferred binding '%s' not found." % name)


def _log(text):
    if QT_VERBOSE:
        sys.stdout.write(text + "\n")


_install()
