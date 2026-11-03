@echo off
cd /d "%~dp0"
title ZhiHui - E-commerce Auto Reply

set "PYEXE="
where python >nul 2>nul && set "PYEXE=python"
if not defined PYEXE (
  where py >nul 2>nul && set "PYEXE=py"
)
if not defined PYEXE (
  echo [ERROR] Python 3.10+ not found in PATH.
  echo Install from https://www.python.org/downloads/ and retry.
  pause
  exit /b 1
)

echo Starting ZhiHui ... the browser will open automatically.
%PYEXE% app.py
if errorlevel 1 pause
