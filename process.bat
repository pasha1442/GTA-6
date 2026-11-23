@echo off
rem Transcribe, review and render 9:16 reels for clips that already exist.
rem     process.bat clips\some-channel
rem     process.bat clips\some-channel\clip.mp4 --force
cd /d "%~dp0"
"%USERPROFILE%\.clipcreator\venv\Scripts\python.exe" -m clipper.process %*
