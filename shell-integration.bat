@echo off

for /f "tokens=*" %%p in ('where pythonw.exe') do (set py_path=%%p)

if not exist "%py_path%" (
	echo "pythonw.exe isn't in PATH"
	exit /b 1
)

set cur_path=%~dp0
set ico_path=%cur_path%qgitc\data\icons\qgitc.ico
set qgitc_path=%cur_path%qgitc.py

reg add "HKEY_CLASSES_ROOT\*\shell\qgitc" /f /ve /t REG_SZ /d qgitc
reg add "HKEY_CLASSES_ROOT\*\shell\qgitc" /f /v Icon /t REG_SZ /d "%ico_path%"
reg add "HKEY_CLASSES_ROOT\*\shell\qgitc\command" /f /ve /t REG_SZ /d "%py_path% \"%qgitc_path%\" -f \"%%1\""

reg add "HKEY_CLASSES_ROOT\Directory\Background\shell\qgitc" /f /ve /t REG_SZ /d qgitc
reg add "HKEY_CLASSES_ROOT\Directory\Background\shell\qgitc" /f /v Icon /t REG_SZ /d "%ico_path%"
reg add "HKEY_CLASSES_ROOT\Directory\Background\shell\qgitc\command" /f /ve /t REG_SZ /d "%py_path% \"%qgitc_path%\" -f \"%%v\""

reg add "HKEY_CLASSES_ROOT\Directory\shell\qgitc" /f /ve /t REG_SZ /d qgitc
reg add "HKEY_CLASSES_ROOT\Directory\shell\qgitc" /f /v Icon /t REG_SZ /d "%ico_path%"
reg add "HKEY_CLASSES_ROOT\Directory\shell\qgitc\command" /f /ve /t REG_SZ /d "%py_path% \"%qgitc_path%\" -f \"%%1\""