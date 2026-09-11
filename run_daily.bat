@echo off
rem 计划任务入口：切换到本目录后执行完整流水线，日志追加到 logs\task.log
cd /d %~dp0
python main.py >> logs\task.log 2>&1
