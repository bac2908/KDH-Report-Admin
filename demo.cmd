@echo off
setlocal
cd /d "%~dp0"
docker compose up -d --wait --wait-timeout 120
if errorlevel 1 (
  echo Khong khoi dong duoc Docker. Hay mo Docker Desktop roi thu lai.
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8090"
