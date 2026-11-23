@echo off
rem Frame selector: choose which part of the video each short shows (webcam, gameplay, face).
rem     frames.bat                         list of all clips\shorts-* folders
rem     frames.bat clips\shorts-VIDEOID    open one folder straight away
rem Opens http://127.0.0.1:8765 in your browser. Ctrl+C here stops it.
cd /d "%~dp0"
"%USERPROFILE%\.clipcreator\venv\Scripts\python.exe" -m clipper.frames %*
