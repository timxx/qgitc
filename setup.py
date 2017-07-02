import sys
import os
import codecs

from setuptools import setup
from distutils.core import Command
from distutils.command.build import build
from distutils.spawn import find_executable, spawn
from distutils.errors import DistutilsExecError
from glob import glob

from PyQt4 import uic
from version import VERSION


class CustomBuild(build):

    def get_sub_commands(self):
        subCommands = super(CustomBuild, self).get_sub_commands()
        subCommands.append("build_qt")
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
        # uic.compileUiDir doesn't works on Windows
        for uiFile in glob("ui/*.ui"):
            pyFile = codecs.open(uiFile[:-3] + ".py", "w+", encoding="utf-8")
            uic.compileUi(uiFile, pyFile)
            pyFile.close()

    def compile_ts(self):
        lrelease = find_executable("lrelease-qt4") or \
            find_executable("lrelease")
        if not lrelease:
            raise DistutilsExecError("Missing lrelease")

        path = os.path.realpath("data/translations/gitc.pro")
        spawn([lrelease, path])


class UpdateTs(Command):
    description = "Update *.ts files"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        lupdate = find_executable("pylupdate4")
        if not lupdate:
            raise DistutilsExecError("Missing pylupdate4")

        path = os.path.realpath("data/translations/gitc.pro")
        spawn([lupdate, path])


class BuildExe(Command):
    description = "Build exe by cx_Freeze"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        spawn([sys.executable, "cxfreeze-setup.py", "build_exe"])
        # remove the unused files
        if sys.platform == "win32":
            import shutil
            import distutils.util

            dirName = "exe.%s-%s" % (distutils.util.get_platform(),
                                     sys.version[0:3])
            baseDir = "build\\" + dirName
            files = [baseDir + "\\Qt*.dll",
                     baseDir + "\\PyQt4\\*.exe"]
            for pattern in files:
                for file in glob(pattern):
                    os.remove(file)

            baseDir += "\\PyQt4"
            dirs = ["doc", "examples", "include", "mkspecs",
                    "uic"]

            for dir in dirs:
                fullPath = baseDir + "\\" + dir
                if os.path.exists(fullPath):
                    shutil.rmtree(fullPath)

            files = ["QtWebKit4.dll", "QtDesigner4.dll",
                     "QtDeclarative4.dll", "QtDesignerComponents4.dll",
                     "QtScript4.dll", "QtCLucene4.dll",
                     "QtScriptTools4.dll", "QtHelp4.dll",
                     "QtTest4.dll"]
            for file in files:
                fullPath = baseDir + "\\" + file
                if os.path.exists(fullPath):
                    os.remove(fullPath)

                fullPath = fullPath.replace("4.dll", ".pyd")
                if os.path.exists(fullPath):
                    os.remove(fullPath)


setup(name='gitc',
      version=VERSION,
      description='A file conflict viewer for git',
      cmdclass=dict(build=CustomBuild,
                    build_qt=BuildQt,
                    build_exe=BuildExe,
                    update_ts=UpdateTs
                    )
      )
