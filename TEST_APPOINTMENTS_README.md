# Test Appointments for Barber Role

This directory contains scripts to create and manage test appointments for the barber role in BarberQMS.

## Purpose

These scripts provide a way to:
1. Create test appointments for testing the barber dashboard and appointments page
2. Clean up test appointments after testing is complete

## Available Scripts

### Python Script (create_test_appointments.py)

This script can be used to create or clean up test appointments for the barber with email `usama@gmail.com`.

Usage:
```bash
# Create test appointments
python create_test_appointments.py --create

# Remove test appointments
python create_test_appointments.py --cleanup

# Create a specific number of test appointments
python create_test_appointments.py --create --count 50
```

### Batch Script (test_appointments.bat)

A Windows batch file for quick access to the Python script functionality.

Usage:
```
test_appointments.bat create   # Create test appointments
test_appointments.bat cleanup  # Remove test appointments
```

## How It Works

- The script creates appointments for the barber spread across the past 7 days and next 7 days
- Each appointment includes:
  - Random time between 9 AM and 6 PM
  - Random customer from a predefined list
  - Random service from the barber's shop
  - Status distribution: 60% scheduled, 30% completed, 10% cancelled
  - For completed appointments, realistic actual start/end times
- All test appointments are marked with "TEST_APPOINTMENT" for easy identification and cleanup
- No actual user accounts are created, only appointment records

## Post-Testing Cleanup

**IMPORTANT**: After testing is complete, make sure to run the cleanup script to remove all test appointments:

```bash
python create_test_appointments.py --cleanup
```

This will safely remove only the test appointments, leaving all real appointments intact.
