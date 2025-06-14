@echo off
REM Script to manage test appointments for BarberQMS

echo BarberQMS Test Appointments Manager

IF "%1"=="create" (
    echo Creating test appointments...
    python create_test_appointments.py --create
    goto end
)

IF "%1"=="cleanup" (
    echo Removing test appointments...
    python create_test_appointments.py --cleanup
    goto end
)

echo Invalid option. Use:
echo   test_appointments.bat create  - to create test appointments
echo   test_appointments.bat cleanup - to remove test appointments

:end
