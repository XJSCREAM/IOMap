@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 echo Run install.bat first.
 pause
 exit /b 1
)
echo Open http://127.0.0.1:5000 in your browser. Keep this window open.
.venv\Scripts\python app.py
pause
