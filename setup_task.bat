@echo off
:: Run this once as Administrator to register the weekly scrape task.
:: To remove: schtasks /delete /tn "MitchamCouncilScraper" /f

set TASK_NAME=MitchamCouncilScraper
set PYTHON=%~dp0.venv\Scripts\python.exe
set SCRIPT=%~dp0scheduled_run.py

echo Registering task: %TASK_NAME%
echo Python: %PYTHON%
echo Script: %SCRIPT%

schtasks /create /tn "%TASK_NAME%" /tr "\"%PYTHON%\" \"%SCRIPT%\"" /sc weekly /d FRI /st 17:00 /f /rl HIGHEST

if %errorlevel% == 0 (
    echo.
    echo Task registered successfully.
    echo It will run every Friday at 5:00 PM.
    echo To run immediately: schtasks /run /tn "%TASK_NAME%"
    echo To view log:        type "%~dp0council_scraper.log"
    echo To delete task:     schtasks /delete /tn "%TASK_NAME%" /f
) else (
    echo.
    echo ERROR: Failed to register task. Try running as Administrator.
)
pause
