@echo off
setlocal
cd /d "%~dp0dashboard" || exit /b 1
if not exist package.json (
  echo ERROR: dashboard\package.json not found.
  exit /b 1
)
npm run dev

