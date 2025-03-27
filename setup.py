import os
import re

from setuptools import (setup, find_packages)
from distutils.core import Command
from distutils.command.build import build
from distutils.spawn import find_executable, spawn
from distutils.errors import DistutilsExecError
from glob import glob
from subprocess import call

from qgitc.version import VERSION


ENV_PATH = None

# find_executable doesn't support `~`
if "PATH" in os.environ:
    paths = os.environ["PATH"].split(os.pathsep)
    ENV_PATH = ""
    for p in paths:
        ENV_PATH += (os.pathsep + p) if ENV_PATH else p
        if p.startswith("~"):
            ENV_PATH += os.pathsep + os.path.expanduser(p)


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
        uic_bin = find_executable("pyside6-uic", ENV_PATH)
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
                             rb") (import .*$)")

        for uiFile in glob("qgitc/*.ui"):
            name = os.path.basename(uiFile)
            pyFile = "qgitc/ui_" + name[:-3] + ".py"
            # "--from-imports" seems no use at all
            spawn([uic_bin, "-g", "python", "-o", pyFile, uiFile])
            self._fix_import(pyFile, pattern)

    def compile_ts(self):
        lrelease = find_executable("pyside6-lrelease", ENV_PATH)
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
            text = pattern.sub(rb"from .\1 \2", line)
            f.write(text)
        f.close()


class UpdateTs(Command):
    description = "Update *.ts files"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        lupdate = find_executable("pyside6-lupdate", ENV_PATH)
        if not lupdate:
            raise DistutilsExecError("Missing pyside6-lupdate")

        call([lupdate, "-extensions", "py,ui", "qgitc",
             "-ts", "qgitc/data/translations/zh_CN.ts"])


with open("README.md", "r") as f:
    long_description = f.read()


setup(name="qgitc",
      version=VERSION,
      author="Weitian Leung",
      author_email="weitianleung@gmail.com",
      description='A file conflict viewer for git',
      long_description_content_type="text/markdown",
      long_description=long_description,
      keywords="git conflict viewer",
      url="https://github.com/timxx/qgitc",
      packages=find_packages(),
      package_data={"qgitc": ["data/icons/*.ico",
                              "data/icons/*.svg",
                              "data/licenses/Apache-2.0.html",
                              "data/translations/*.qm",
                              "data/templates/*.xlsx"
                              ]},
      license="Apache",
      python_requires='>=3.0',
      entry_points={
          "gui_scripts": [
              "qgitc=qgitc.main:main",
              "imgdiff=mergetool.imgdiff:main"
          ]
      },
      install_requires=[
          "PySide6-Essentials>=6.3.0; sys_platform != 'linux'",
          "PySide6>=6.2.0; sys_platform == 'linux'",
          "chardet", "requests",
          "psutil; sys_platform == 'win32'"
      ],
      classifiers=[
          "License :: OSI Approved :: Apache Software License",
          "Operating System :: POSIX",
          "Operating System :: POSIX :: BSD",
          "Operating System :: POSIX :: Linux",
          "Operating System :: Microsoft :: Windows",
          "Programming Language :: Python :: 3",
      ],
      cmdclass=dict(build=CustomBuild,
                    build_qt=BuildQt,
                    update_ts=UpdateTs
                    )
      )
