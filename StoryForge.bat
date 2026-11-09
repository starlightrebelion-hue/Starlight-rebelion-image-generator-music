@echo off
rem Abre StoryForge (Ejemplo 1) en el navegador. Cerrar esta ventana apaga el servidor.
cd /d "%~dp0"
".venv\Scripts\python.exe" storyforge.py
pause
