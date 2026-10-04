@echo off
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python -m pip install -r requirements.lock.txt
if errorlevel 1 goto failed
echo Python dependencies installed. Install Tesseract and add it to PATH for OCR.
echo Optional translation model: .venv\Scripts\python download_model.py
pause
exit /b 0
:failed
echo Installation failed. Check the error above.
pause
exit /b 1
