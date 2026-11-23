@echo off
rem Make YouTube Shorts / Instagram Reels with subtitles from a YouTube link or a video file.
rem     shorts.bat "https://www.youtube.com/watch?v=VIDEOID"
rem     shorts.bat "C:\path\to\video.mp4" --count 3
cd /d "%~dp0"
"%USERPROFILE%\.clipcreator\venv\Scripts\python.exe" -m clipper.shorts %*
