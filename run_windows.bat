@echo off
cd /d %~dp0
if not exist .venv py -m venv .venv
call .venv\Scripts\activate
python -m pip install -r requirements.txt
if not exist .env copy .env.example .env
python run.py
pause
