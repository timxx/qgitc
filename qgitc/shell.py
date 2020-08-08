# -*- coding: utf-8 -*-
import sys
import os

if sys.platform == "win32":
    from winreg import (
        CreateKeyEx,
        SetValueEx,
        DeleteKeyEx,
        HKEY_CLASSES_ROOT,
        REG_SZ)
else:
    import xml.etree.ElementTree as ET
    from datetime import datetime

    from .common import isXfce4


def _exePath():
    exePath = os.path.abspath(sys.argv[0])

    def _quote(path):
        if " " in path:
            return '"' + path + '"'
        return path

    if exePath.endswith("qgitc.py"):
        if sys.platform == "win32":
            pyExe = _quote(sys.executable.replace(".exe", "w.exe"))
        else:
            pyExe = _quote(sys.executable)
        exePath = pyExe + ' ' + _quote(exePath)
    else:
        if sys.platform == "win32":
            if not exePath.endswith(".exe"):
                exePath += ".exe"
        exePath = _quote(exePath)
    return exePath


def _dataDir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _shell_usage(args):
    print("Usage:\n"
          "\tqgitc shell regitser\n"
          "\tqgitc shell unregister")


def _shell_register_win(args):

    def _do_register(subkey, name, ico, exe, cmd="log", arg="%1"):
        with CreateKeyEx(HKEY_CLASSES_ROOT, subkey) as key:
            SetValueEx(key, "", 0, REG_SZ, name)
            SetValueEx(key, "Icon", 0, REG_SZ, ico)

        with CreateKeyEx(HKEY_CLASSES_ROOT, subkey + "\\command") as key:
            if arg:
                value = '{} {} "{}"'.format(exe, cmd, arg)
            else:
                value = '{} {}'.format(exe, cmd)
            SetValueEx(key, "", 0, REG_SZ, value)

        return 0

    ico = os.path.join(_dataDir(), "icons", "qgitc.ico")
    exe = _exePath()

    ret = _do_register(r"*\shell\QGitc", "QGitc", ico, exe)
    ret |= _do_register(r"Directory\Background\shell\QGitc",
                        "QGitc", ico, exe, arg=None)
    ret |= _do_register(r"Directory\shell\QGitc", "QGitc", ico, exe)
    ret |= _do_register(r"*\shell\QGitcBlame",
                        "QGitc Blame", ico, exe, "blame")

    return ret


def _shell_unregister_win(args):

    def _do_delete(subkey):
        try:
            DeleteKeyEx(HKEY_CLASSES_ROOT, subkey)
            return 0
        except FileNotFoundError:
            return 0
        return 1

    ret = _do_delete(r"*\shell\QGitc\command")
    ret |= _do_delete(r"*\shell\QGitc")

    ret |= _do_delete(r"Directory\Background\shell\QGitc\command")
    ret |= _do_delete(r"Directory\Background\shell\QGitc")

    ret |= _do_delete(r"Directory\shell\QGitc\command")
    ret |= _do_delete(r"Directory\shell\QGitc")

    ret |= _do_delete(r"*\shell\QGitcBlame\command")
    ret |= _do_delete(r"*\shell\QGitcBlame")

    return ret


def _shell_register_linux(args):
    if args.file_manager == "thunar" or isXfce4():
        return _register_xfce4(args)

    print("Unsupported desktop!")
    return 1


def _shell_unregister_linux(args):
    if args.file_manager == "thunar" or isXfce4():
        return _unregister_xfce4(args)

    print("Unsupported desktop!")
    return 1


# use custom action for thunar
def _register_xfce4(args):
    dir = os.path.join(os.path.expanduser("~"), ".config", "Thunar")
    if not os.path.exists(dir):
        os.makedirs(dir)

    uca = os.path.join(dir, "uca.xml")
    if not os.path.exists(uca):
        pass
    else:
        # remove first
        _unregister_xfce4(args)

    tree = ET.parse(uca)
    root = tree.getroot()

    action = ET.Element("action")
    action.text = "\n\t"
    action.tail = "\n"

    def _addElement(name, text=None, withTab=True):
        e = ET.Element(name)
        if text is not None:
            e.text = text
        # for indent LoL
        if withTab:
            e.tail = "\n\t"
        else:
            e.tail = "\n"
        action.append(e)

    def _uniqueId():
        stamp = datetime.now().timestamp()
        return "{}-1".format(int(stamp * 1000000))

    ico = os.path.join(_dataDir(), "icons", "qgitc.svg")

    _addElement("icon", ico)
    _addElement("name", "QGitc")
    _addElement("unique-id", _uniqueId())
    _addElement("command", '%s log %%f' % _exePath())
    _addElement("description", "Run QGitc")
    _addElement("patterns", "*")
    _addElement("directories")
    _addElement("audio-files")
    _addElement("image-files")
    _addElement("other-files")
    _addElement("text-files")
    _addElement("video-files", withTab=False)

    root.append(action)

    action = ET.Element("action")
    action.text = "\n\t"
    action.tail = "\n"

    _addElement("icon", ico)
    _addElement("name", "QGitc Blame")
    _addElement("unique-id", _uniqueId())
    _addElement("command", '%s blame %%f' % _exePath())
    _addElement("description", "Run QGitc Blame")
    _addElement("patterns", "*")
    _addElement("other-files")
    _addElement("text-files", withTab=False)

    root.append(action)

    tree.write(uca, xml_declaration=True, encoding="utf-8")

    return 0


def _unregister_xfce4(args):
    uca = os.path.join(os.path.expanduser("~"), ".config", "Thunar", "uca.xml")
    if not os.path.exists(uca):
        return 0

    tree = ET.parse(uca)
    root = tree.getroot()

    def _remove(name):
        items = root.findall("./action[name='%s']" % name)
        for item in items:
            root.remove(item)

    _remove("QGitc")
    _remove("QGitc Blame")

    tree.write(uca, xml_declaration=True, encoding="utf-8")

    return 0


def setup_shell_args(parser):
    shell = parser.add_parser(
        "shell", help="Shell integration")
    shell.set_defaults(func=_shell_usage)

    subparser = shell.add_subparsers(
        title="Operation", metavar="")

    reg_parser = subparser.add_parser(
        "register", help="Register shell")
    unreg_parser = subparser.add_parser(
        "unregister", help="Unregister shell")

    if sys.platform == "win32":
        reg_parser.set_defaults(func=_shell_register_win)
        unreg_parser.set_defaults(func=_shell_unregister_win)
    else:
        supported_fm = ["thunar"]
        reg_parser.add_argument(
            "-m", "--file-manager",
            metavar="<file manager>",
            choices=supported_fm,
            help="Register for specify file manager")

        unreg_parser.add_argument(
            "-m", "--file-manager",
            metavar="<file manager>",
            choices=supported_fm,
            help="Unregister for specify file manager")

        reg_parser.set_defaults(func=_shell_register_linux)
        unreg_parser.set_defaults(func=_shell_unregister_linux)
