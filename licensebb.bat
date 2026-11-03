@echo off
REM ======================================================================
REM  SUG/SRC e-Voting System - LICENSE FILE
REM  Do not edit, rename, move or delete this file.
REM  Any change locks the application until a valid license is restored.
REM ======================================================================
REM PRODUCT: SUG/SRC e-Voting System
REM LICENSE-ID: C401868AB4AC
REM LICENSEE: 360 Global Network Limited
REM ISSUED: 2026-11-02
REM EXPIRES: 2026-12-03
REM SIGNATURE: 1XBZKf8btOhhJiBMLolm0Irz0ZxaSBU4INnj3fa1Pwe6hMBWCxEPXT92YOlg1kiyw7VBan1tWUJyfh5OZPv5Ag==
set "PY=python"
if exist "%~dp0backend\.venv\Scripts\python.exe" set "PY=%~dp0backend\.venv\Scripts\python.exe"
"%PY%" "%~dp0backend\license_tool.py" status
pause
