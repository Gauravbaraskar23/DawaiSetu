@echo off
cd /d "F:\MediTrack"
call venv\Scripts\activate.bat
python manage.py send_expiry_reminders
python manage.py sync_staff_limits
python manage.py send_refill_reminders