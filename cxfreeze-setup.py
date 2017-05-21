import sys

from glob import glob
from cx_Freeze import setup, Executable
from version import VERSION

# Dependencies are automatically detected, but it might need
# fine tuning.
excludes = ["Tkinter"]
includes = ["logview", "colorwidget"]
includeFiles = [("data/icons/gitc.svg", "data/icons/gitc.svg"),
                ("data/licenses/Apache-2.0.html", "data/licenses/Apache-2.0.html"),
                ("LICENSE", "data/licenses/LICENSE")]

for qm in glob("data/translations/*.qm"):
    includeFiles.append((qm, qm))

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
      version=VERSION,
      description='A file conflict viewer for git',
      options=dict(build_exe=buildOptions),
      executables=executables,
      )
