@echo off
rem Genera un tema de cero. Ejemplos: agente_musical.bat --n 3   /   agente_musical.bat --semilla 123
rem Opciones: --motor azar (sin Ollama), --sin-fl (solo .mid y ficha), --modelo NOMBRE
cd /d "%~dp0"
".venv\Scripts\python.exe" agente_musical.py %*
pause
