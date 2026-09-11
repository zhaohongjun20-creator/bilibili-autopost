@echo off
chcp 65001 >nul
cd /d %~dp0
schtasks /Create /TN "bilibili-autopost" /TR "%CD%\run_daily.bat" /SC DAILY /ST 10:00 /F
echo.
echo 已安装每日 10:00 计划任务。
echo 查看: schtasks /Query /TN bilibili-autopost
echo 卸载: schtasks /Delete /TN bilibili-autopost /F
pause
