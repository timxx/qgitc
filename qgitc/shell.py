# -*- coding: utf-8 -*-
import os
import sys

if sys.platform == "win32":
    from winreg import HKEY_CURRENT_USER, REG_SZ, CreateKeyEx, DeleteKeyEx, SetValueEx
else:
    import xml.etree.ElementTree as ET
    from datetime import datetime

    from qgitc.common import isXfce4


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
        with CreateKeyEx(HKEY_CURRENT_USER, subkey) as key:
            SetValueEx(key, "MUIVerb", 0, REG_SZ, name)
            if ico:
                SetValueEx(key, "Icon", 0, REG_SZ, ico)

        with CreateKeyEx(HKEY_CURRENT_USER, subkey + "\\command") as key:
            if arg:
                value = '{} {} "{}"'.format(exe, cmd, arg)
            else:
                value = '{} {}'.format(exe, cmd)
            SetValueEx(key, "", 0, REG_SZ, value)

        return 0

    def _create_menu(subkey, name, ico):
        with CreateKeyEx(HKEY_CURRENT_USER, subkey) as key:
            SetValueEx(key, "MUIVerb", 0, REG_SZ, name)
            SetValueEx(key, "Icon", 0, REG_SZ, ico)
            SetValueEx(key, "SubCommands", 0, REG_SZ, "")
        return 0

    ico = os.path.join(_dataDir(), "icons", "qgitc.ico")
    exe = _exePath()

    ret = _create_menu(r"Software\Classes\*\shell\QGitc", "QGitc", ico)
    ret |= _do_register(r"Software\Classes\*\shell\QGitc\shell\Log", "Log", None, exe)
    ret |= _do_register(r"Software\Classes\*\shell\QGitc\shell\Blame", "Blame", None, exe, "blame")
    ret |= _do_register(r"Software\Classes\*\shell\QGitc\shell\Commit", "Commit", None, exe, "commit", None)

    ret |= _do_register(r"Software\Classes\*\shell\QGitc\shell\Chat", "Chat", None, exe, "chat", None)
    ret |= _do_register(r"Software\Classes\*\shell\QGitc\shell\Chat", "Chat", None, exe, "chat", None)

    ret |= _create_menu(r"Software\Classes\Directory\Background\shell\QGitc", "QGitc", ico)
    ret |= _do_register(r"Software\Classes\Directory\Background\shell\QGitc\shell\Log", "Log", None, exe, arg=None)
    ret |= _do_register(r"Software\Classes\Directory\Background\shell\QGitc\shell\Commit", "Commit", None, exe, "commit", None)
    ret |= _do_register(r"Software\Classes\Directory\Background\shell\QGitc\shell\Chat", "Chat", None, exe, "chat", None)

    ret |= _create_menu(r"Software\Classes\Directory\shell\QGitc", "QGitc", ico)
    ret |= _do_register(r"Software\Classes\Directory\shell\QGitc\shell\Log", "Log", None, exe)
    ret |= _do_register(r"Software\Classes\Directory\shell\QGitc\shell\Commit", "Commit", None, exe, "commit", None)
    ret |= _do_register(r"Software\Classes\Directory\shell\QGitc\shell\Chat", "Chat", None, exe, "chat", None)

    return ret


def _shell_unregister_win(args):

    def _do_delete(subkey):
        try:
            DeleteKeyEx(HKEY_CURRENT_USER, subkey)
            return 0
        except FileNotFoundError:
            return 0
        return 1

    ret = 0
    file_cmds = ["log", "blame", "commit", "chat"]
    for cmd in file_cmds:
        ret |= _do_delete(r"Software\Classes\*\shell\QGitc\shell\{}\command".format(cmd))
        ret |= _do_delete(r"Software\Classes\*\shell\QGitc\shell\{}".format(cmd))

    ret |= _do_delete(r"Software\Classes\*\shell\QGitc\shell")
    ret |= _do_delete(r"Software\Classes\*\shell\QGitc")

    dir_cmds = ["log", "commit", "chat"]
    for cmd in dir_cmds:
        ret |= _do_delete(r"Software\Classes\Directory\Background\shell\QGitc\shell\{}\command".format(cmd))
        ret |= _do_delete(r"Software\Classes\Directory\Background\shell\QGitc\shell\{}".format(cmd))

        ret |= _do_delete(r"Software\Classes\Directory\shell\QGitc\shell\{}\command".format(cmd))
        ret |= _do_delete(r"Software\Classes\Directory\shell\QGitc\shell\{}".format(cmd))

    ret |= _do_delete(r"Software\Classes\Directory\Background\shell\QGitc\shell")
    ret |= _do_delete(r"Software\Classes\Directory\Background\shell\QGitc")

    ret |= _do_delete(r"Software\Classes\Directory\shell\QGitc\shell")
    ret |= _do_delete(r"Software\Classes\Directory\shell\QGitc")

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
