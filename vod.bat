@echo off
rem Make clips from a recorded video (a finished YouTube stream or a file on disk).
rem     vod.bat "https://www.youtube.com/watch?v=VIDEOID"
rem     vod.bat "C:\path\to\video.mp4" --top 3
cd /d "%~dp0"
"%USERPROFILE%\.clipcreator\venv\Scripts\python.exe" -m clipper.vod %*
