@echo off
title Pulse Social Network

if not exist "pulse.db" (
    echo Creating database...
)

if not exist "venv" (
    echo Installing dependencies...
    python -m venv venv
    call venv\Scripts\activate
    pip install flask flask-session
)

call venv\Scripts\activate
python app.py
pause