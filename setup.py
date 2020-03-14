import sys
import os
import codecs

from setuptools import (setup, find_packages)
from distutils.core import Command
from distutils.command.build import build
from distutils.spawn import find_executable, spawn
from distutils.errors import DistutilsExecError
from glob import glob

from PyQt5 import uic
from PyQt5 import QtCore
from gitc.version import VERSION


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
        return # tempory disabled
        # uic.compileUiDir doesn't works on Windows
        for uiFile in glob("gitc/*.ui"):
            name = os.path.basename(uiFile)
            pyFile = codecs.open(
                "gitc/ui_" + name[:-3] + ".py", "w+", encoding="utf-8")
            uic.compileUi(uiFile, pyFile)
            pyFile.close()

    def compile_ts(self):
        lrelease = find_executable(
            "lrelease-qt5") or find_executable("lrelease")
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
        lupdate = find_executable("pylupdate5")
        if not lupdate:
            raise DistutilsExecError("Missing pylupdate5")

        path = os.path.realpath("data/translations/gitc.pro")
        spawn([lupdate, path])


with open("README.md", "r") as f:
    long_description = f.read()


setup(name="gitc",
      version=VERSION,
      author="Weitian Leung",
      author_email="weitianleung@gmail.com",
      description='A file conflict viewer for git',
      long_description_content_type="text/markdown",
      long_description=long_description,
      keywords="git conflict viewer",
      url="https://github.com/timxx/gitc",
      packages=find_packages(),
      #package_data={"gitc": ["data/icons/*",
      #                       "data/licenses/Apache-2.0.html",
      #                       "data/translations/*.qm"
      #                       ]},
      license="Apache",
      python_requires='>=3.0',
      entry_points={
          "console_scripts": [
              "gitc=gitc.main:main",
              "imgdiff=mergetool.imgdiff:main"
          ]
      },
      install_requires=["PyQt5"],
      cmdclass=dict(build=CustomBuild,
                    build_qt=BuildQt,
                    update_ts=UpdateTs
                    )
      )
