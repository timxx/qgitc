import sys
import os

from setuptools import setup
from distutils.core import Command
from distutils.command.build import build
from distutils.spawn import find_executable, spawn
from distutils.errors import DistutilsExecError

from PyQt4 import uic


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
        uiDir = os.path.realpath("ui")
        uic.compileUiDir(uiDir)

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


setup(name='gitc',
      version='1.0',
      description='A file conflict viewer for git',
      cmdclass=dict(build=CustomBuild,
          build_qt=BuildQt,
          build_exe=BuildExe,
          update_ts=UpdateTs
          )
      )
