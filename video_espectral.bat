@echo off
rem Arma el video de un tema. Se puede soltar el audio sobre este archivo.
rem Ejemplo: video_espectral.bat "tema.mp3" --semilla 7 --paleta Plasma --idea "ciudad bajo la lluvia"
rem Opciones: --desde 60 --segundos 15 (prueba corta), --sin-comfy (sin wallpapers), --alto 2160, --fps 30
cd /d "%~dp0"
".venv\Scripts\python.exe" video_espectral.py %*
pause
