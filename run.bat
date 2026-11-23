@echo off
rem Starts the clipper. Channels come from config.json, or pass them here:
rem     run.bat channel1 channel2
set "VENV=%USERPROFILE%\.clipcreator\venv"
if not exist "%VENV%\Scripts\python.exe" (
    echo Setting up Python environment in %VENV% ...
    python -m venv "%VENV%" || exit /b 1
    "%VENV%\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r "%~dp0requirements.txt" || exit /b 1
)
cd /d "%~dp0"
"%VENV%\Scripts\python.exe" -m clipper %*
