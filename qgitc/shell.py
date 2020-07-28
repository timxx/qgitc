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


def _shell_usage(args):
    print("Usage:\n"
          "\tqgitc shell regitser\n"
          "\tqgitc shell unregister")


def _shell_register(args):

    def _do_register(subkey, name, ico, exe, cmd="log", arg="%1"):
        with CreateKeyEx(HKEY_CLASSES_ROOT, subkey) as key:
            SetValueEx(key, "", 0, REG_SZ, name)
            SetValueEx(key, "Icon", 0, REG_SZ, ico)

        with CreateKeyEx(HKEY_CLASSES_ROOT, subkey + "\\command") as key:
            value = '{} {} "{}"'.format(exe, cmd, arg)
            SetValueEx(key, "", 0, REG_SZ, value)

        return 0

    def _exePath():
        exePath = os.path.abspath(sys.argv[0])
        if exePath.endswith("qgitc.py"):
            pyExe = '"' + sys.executable.replace(".exe", "w.exe") + '"'
            exePath = pyExe + ' "' + exePath + '"'
        else:
            if not exePath.endswith(".exe"):
                exePath += ".exe"
            exePath = '"' + exePath + '"'
        return exePath

    dataDir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    ico = os.path.join(dataDir, "icons", "qgitc.ico")
    exe = _exePath()

    ret = _do_register(r"*\shell\QGitc", "QGitc", ico, exe)
    ret |= _do_register(r"Directory\Background\shell\QGitc",
                        "QGitc", ico, exe, arg="%v")
    ret |= _do_register(r"Directory\shell\QGitc", "QGitc", ico, exe)
    ret |= _do_register(r"*\shell\QGitcBlame",
                        "QGitc Blame", ico, exe, "blame")

    return ret


def _shell_unregister(args):

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


def setup_shell_args(parser):
    shell = parser.add_parser(
        "shell", help="Shell integration")
    shell.set_defaults(func=_shell_usage)

    subparser = shell.add_subparsers(
        title="Operation", metavar="")

    reg_parser = subparser.add_parser(
        "register", help="Register shell")
    reg_parser.set_defaults(func=_shell_register)

    unreg_parser = subparser.add_parser(
        "unregister", help="Unregister shell")
    unreg_parser.set_defaults(func=_shell_unregister)
