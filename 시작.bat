@echo off
title Ultraformer MPT 분석 대시보드
cd /d "%~dp0"

echo ====================================
echo  Ultraformer MPT 분석 대시보드
echo ====================================
echo.
echo Flask 설치 확인 중...
pip install flask -q 2>nul
echo.
echo 서버를 시작합니다...
echo 브라우저가 자동으로 열립니다.
echo.
echo 종료하려면 이 창을 닫으세요.
echo ====================================
echo.
python server.py
pause
