import os
import re
import shutil
from distutils.command.build import build
from distutils.core import Command
from distutils.errors import DistutilsExecError
from distutils.spawn import spawn
from glob import glob
from subprocess import call

from setuptools import setup

ENV_PATH = None


# find_executable doesn't support `~`
if "PATH" in os.environ:
    paths = os.environ["PATH"].split(os.pathsep)
    ENV_PATH = ""
    for p in paths:
        ENV_PATH += (os.pathsep + p) if ENV_PATH else p
        if p.startswith("~"):
            ENV_PATH += os.pathsep + os.path.expanduser(p)


def _find_qt_tool(toolSuffix: str):
    tool = shutil.which(f"pyside6-{toolSuffix}", path=ENV_PATH)
    if not tool:
        tool = shutil.which(toolSuffix, path=ENV_PATH)
    return tool


class CustomBuild(build):

    def get_sub_commands(self):
        subCommands = super(CustomBuild, self).get_sub_commands()
        subCommands.insert(0, "build_qt")
        return subCommands


class BuildQt(Command):
    description = "Build Qt files"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        methos = ("ui", "ts")
        for m in methos:
            getattr(self, "compile_" + m)()

    def compile_ui(self):
        uic_bin = _find_qt_tool("uic")
        if not uic_bin:
            raise DistutilsExecError("Missing uic")

        pattern = re.compile(rb"from (diffview"
                             rb"|logview"
                             rb"|waitingspinnerwidget"
                             rb"|gitview"
                             rb"|colorwidget"
                             rb"|linkeditwidget"
                             rb"|coloredicontoolbutton"
                             rb"|patchviewer"
                             rb"|emptystatelistview"
                             rb"|commitmessageedit"
                             rb"|menubutton"
                             rb"|commitactionwidget"
                             rb"|fontchooserwidget"
                             rb") (import .*$)")

        for uiFile in glob("qgitc/*.ui"):
            name = os.path.basename(uiFile)
            pyFile = "qgitc/ui_" + name[:-3] + ".py"
            # "--from-imports" seems no use at all
            spawn([uic_bin, "-g", "python", "-o", pyFile, uiFile])
            self._fix_import(pyFile, pattern)

    def compile_ts(self):
        lrelease = _find_qt_tool("lrelease")
        if not lrelease:
            print("Missing lrelease, no translation will be built.")
            return

        path = os.path.realpath("qgitc/data/translations/qgitc.json")
        call([lrelease, "-project", path], cwd="qgitc/data/translations")

    def _fix_import(self, pyFile, pattern):
        f = open(pyFile, "rb")
        lines = f.readlines()
        f.close()

        f = open(pyFile, "wb+")
        for line in lines:
            text = pattern.sub(rb"from qgitc.\1 \2", line)
            f.write(text)
        f.close()


class UpdateTs(Command):
    description = "Update *.ts files"
    user_options = [
        ("no-obsolete", None, "Drop all obsolete and vanished strings")
    ]

    def initialize_options(self):
        self.no_obsolete = False

    def finalize_options(self):
        pass

    def run(self):
        lupdate = _find_qt_tool("lupdate")
        if not lupdate:
            raise DistutilsExecError("Missing lupdate")

        cmd = [lupdate, "-extensions", "py,ui", "qgitc", "-ts", "qgitc/data/translations/zh_CN.ts"]
        if self.no_obsolete:
            cmd.append("-no-obsolete")
        call(cmd)


with open("README.md", "r") as f:
    long_description = ""
    pattern = re.compile(r"\./screenshots/(.*\.png)")
    for line in f.readlines():
        long_description += pattern.sub(
            "https://raw.githubusercontent.com/timxx/qgitc/refs/heads/master/screenshots/\\1", line)


setup(
    long_description_content_type="text/markdown",
    long_description=long_description,
    cmdclass=dict(build=CustomBuild,
                  build_qt=BuildQt,
                  update_ts=UpdateTs
                  )
)
