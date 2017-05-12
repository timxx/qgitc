import sys

from glob import glob
from cx_Freeze import setup, Executable

# Dependencies are automatically detected, but it might need
# fine tuning.
excludes=["Tkinter"]
includes = ["logview", "colorwidget"]
includeFiles = [("data/icons/gitc.svg", "data/icons/gitc.svg")]

for qm in glob("data/translations/*.qm"):
    includeFiles.append((qm, qm))

# FIXME: find a better way merge ui files
for ui in glob("ui/*.py"):
    includeFiles.append((ui, ui))

buildOptions = dict(
    packages=[],
    excludes=excludes,
    includes=includes,
    include_files=includeFiles,
    include_msvcr=True,
    silent=True)

base = None
icon = None
if sys.platform == "win32":
    base = "Win32GUI"
    icon = "data/icons/gitc.ico"

executables = [
    Executable('gitc',
               base=base,
               icon=icon
               )]

setup(name='gitc',
      version='1.0',
      description='A file conflict viewer for git',
      options=dict(build_exe=buildOptions),
      executables=executables,
      )
