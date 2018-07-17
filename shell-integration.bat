@echo off

for /f "tokens=*" %%p in ('where pythonw.exe') do (set py_path=%%p)

if not exist "%py_path%" (
	echo "pythonw.exe isn't in PATH"
	exit /b 1
)

set cur_path=%~dp0
set ico_path=%cur_path%data\icons\gitc.ico
set gitc_path=%cur_path%gitc

reg add "HKEY_CLASSES_ROOT\*\shell\gitc" /f /ve /t REG_SZ /d gitc
reg add "HKEY_CLASSES_ROOT\*\shell\gitc" /f /v Icon /t REG_SZ /d "%ico_path%"
reg add "HKEY_CLASSES_ROOT\*\shell\gitc\command" /f /ve /t REG_SZ /d "%py_path% \"%gitc_path%\" -f \"%%1\""

reg add "HKEY_CLASSES_ROOT\Directory\Background\shell\gitc" /f /ve /t REG_SZ /d gitc
reg add "HKEY_CLASSES_ROOT\Directory\Background\shell\gitc" /f /v Icon /t REG_SZ /d "%ico_path%"
reg add "HKEY_CLASSES_ROOT\Directory\Background\shell\gitc\command" /f /ve /t REG_SZ /d "%py_path% \"%gitc_path%\" -f \"%%v\""

reg add "HKEY_CLASSES_ROOT\Directory\shell\gitc" /f /ve /t REG_SZ /d gitc
reg add "HKEY_CLASSES_ROOT\Directory\shell\gitc" /f /v Icon /t REG_SZ /d "%ico_path%"
reg add "HKEY_CLASSES_ROOT\Directory\shell\gitc\command" /f /ve /t REG_SZ /d "%py_path% \"%gitc_path%\" -f \"%%1\""