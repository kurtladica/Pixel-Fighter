@echo off
rem Double-click this file to play Pixel Fighter.
rem It moves into the game folder first so main.py can find the assets.
cd /d "%~dp0"
title Pixel Fighter
python main.py
echo.
echo The game has closed. If you saw an error above, read it and try again.
pause