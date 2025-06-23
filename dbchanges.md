# Database Schema Changes

## Overview
Major refactoring to normalize the database schema and improve naming conventions.

## Table Renames
1. `shops` → `businesses`
2. `shop_operating_hours` → `business_operating_hours` 
3. `barbers` → `employees`
4. `barber_services` → `employee_services`
5. `barber_schedules` → `employee_schedules`

## Tables Deleted
1. `work_schedules` - Redundant with business_operating_hours
2. `schedule_breaks` - Moved to employee_schedules and business_operating_hours
3. `employee_schedules` (junction table) - No longer needed

## New Tables Created

### 1. `business_advertisements`
**Purpose**: Moved advertisement functionality from businesses table
**Fields**:
- `id` (Primary Key)
- `business_id` (Foreign Key to businesses)
- `image_url` (String, required)
- `start_date` (DateTime, required)
- `end_date` (DateTime, required)
- `is_active` (Boolean, default=True)
- `created_at` (DateTime, auto-generated)

### 2. `contact_messages`
**Purpose**: Handle contact form submissions separately from feedback
**Fields**:
- `id` (Primary Key)
- `subject` (String, required)
- `message` (Text, required)
- `email` (String, optional)
- `phone_number` (String, optional)
- `created_at` (DateTime, auto-generated)

### 3. `business_operating_hours`
**Purpose**: Detailed operating hours per day of week
**Fields**:
- `id` (Primary Key)
- `business_id` (Foreign Key to businesses)
- `day_of_week` (Integer: 0=Sunday, 1=Monday, ..., 6=Saturday)
- `opening_time` (Time, nullable if closed)
- `closing_time` (Time, nullable if closed)
- `is_closed` (Boolean, default=False)
- `lunch_break_start` (Time, nullable)
- `lunch_break_end` (Time, nullable)
- **Unique constraint**: `business_id` + `day_of_week`

## Field Changes

### Businesses Table (formerly shops)
**Removed:**
- `opening_time` - Redundant with business_operating_hours
- `closing_time` - Redundant with business_operating_hours  
- `advertisement_image_url` - Moved to business_advertisements
- `advertisement_start_date` - Moved to business_advertisements
- `advertisement_end_date` - Moved to business_advertisements
- `is_advertisement_active` - Moved to business_advertisements
- `has_advertisement` - Moved to business_advertisements

**Added:**
- `description` (Text) - Business description
- `logo_url` (String) - Business logo

**Kept:**
- `is_open_24_hours` - For 24-hour functionality

### Business_Operating_Hours Table (formerly shop_operating_hours)
**Changed:**
- `shop_id` → `business_id`

**Added:**
- `lunch_break_start` (Time, nullable) - Business-wide lunch break
- `lunch_break_end` (Time, nullable) - Business-wide lunch break

### Employees Table (formerly barbers)
**Changed:**
- `shop_id` → `business_id`

### Employee_Schedules Table (formerly barber_schedules)
**Complete restructure:**

**Removed:**
- `start_date` - Replace with day_of_week system
- `end_date` - Replace with day_of_week system  
- `repeat_frequency` - Not needed with day_of_week system

**Changed:**
- `barber_id` → `employee_id`

**Added:**
- `day_of_week` (Integer) - 0-6 for Sunday-Saturday
- `start_time` (Time) - Daily start time
- `end_time` (Time) - Daily end time
- `lunch_break_start` (Time, nullable) - Personal lunch break
- `lunch_break_end` (Time, nullable) - Personal lunch break
- `is_working` (Boolean, default=True) - Whether working that day

### Services Table
**Changed:**
- `shop_id` → `business_id`

**Added:**
- `is_active` (Boolean, default=True) - To disable services without deleting
- `category` (String, nullable) - Service categorization

### Appointments Table
**Changed:**
- `shop_id` → `business_id`
- `barber_id` → `employee_id`

**Added:**
- `total_duration` (Integer) - Calculated from services
- `total_price` (Float) - Calculated from services
- `notes` (Text, nullable) - Special instructions

**Modified:**
- `custom_duration` - For changing duration for specific appointment only
- `custom_price` - For changing price for specific appointment only

### Queue_Entry Table
**Changed:**
- `shop_id` → `business_id`
- `barber_id` → `employee_id`

**Added:**
- `estimated_service_time` (DateTime) - When service is expected to start
- `notes` (Text, nullable) - Special instructions

**Modified:**
- `custom_duration` - For changing duration for specific queue entry only
- `custom_price` - Change of price for that entry only

### Feedback Table
**Changed:**
- `shop_id` → `business_id`
- `barber_id` → `employee_id`
- `comments` → `message` - For consistency

**Added:**
- `subject` (String, nullable) - Message subject

### ScheduleOverride Table
**Changed:**
- `shop_id` → `business_id`
- `barber_id` → `employee_id`

**Added:**
- `reason` (String) - Why the override exists
- `override_type` (Enum) - HOLIDAY, SPECIAL_EVENT, EMERGENCY, etc.

## Enum Changes
1. `BarberStatus` → `EmployeeStatus`
2. **New Enum Added**: `OverrideType` with values:
   - `HOLIDAY`
   - `SPECIAL_EVENT` 
   - `EMERGENCY`
   - `PERSONAL`
   - `SICK_LEAVE`

## Foreign Key Updates
All references updated:
- `shop_id` → `business_id`
- `barber_id` → `employee_id`

## Complete Field Rename Reference (Critical for Frontend)

### Tables with `shop_id` → `business_id` changes:
- `employees` (formerly barbers)
- `appointments`
- `queue_entries`
- `feedbacks`
- `services`
- `schedule_overrides`

### Tables with `barber_id` → `employee_id` changes:
- `employee_services` (formerly barber_services)
- `appointments`
- `queue_entries`
- `feedbacks`
- `employee_schedules` (formerly barber_schedules)
- `schedule_overrides`

### Other Field Renames:
- `feedbacks.comments` → `feedbacks.message`

## API Endpoint Changes

### Router File Changes:
- `barbers.py` → `employees.py` (new file created)
- `shop_owners.py` → `business_owners.py` (already existed, updated)
- `schedules.py` → **DELETED** (functionality moved to employees.py)

### API Endpoint Path Changes:
- `/shops/` → `/businesses/`
- `/barbers/` → `/employees/`
- `/shop-owners/` → `/business-owners/`

### Specific Endpoint Updates:
- `POST /businesses/` (formerly `/shops/`)
- `GET /businesses/` (formerly `/shops/`)
- `GET /businesses/{business_id}` (formerly `/shops/{shop_id}`)
- `PUT /businesses/{business_id}` (formerly `/shops/{shop_id}`)
- `DELETE /businesses/{business_id}` (formerly `/shops/{shop_id}`)
- `POST /employees/` (formerly `/barbers/`)
- `GET /employees/` (formerly `/barbers/`)
- `GET /employees/{employee_id}` (formerly `/barbers/{barber_id}`)
- `PUT /employees/{employee_id}` (formerly `/barbers/{barber_id}`)
- `DELETE /employees/{employee_id}` (formerly `/barbers/{barber_id}`)

### Request/Response Body Field Changes:
All JSON payloads now use:
- `business_id` instead of `shop_id`
- `employee_id` instead of `barber_id`
- `message` instead of `comments` (in feedback endpoints)
- New fields available in responses (see Field Changes section above)

## Migration Notes
- This requires a new Alembic migration
- Data migration scripts needed for existing data
- All API clients will need to update to new field names
- Frontend will need comprehensive updates to match new schema

## Frontend Update Checklist

### 🔴 Critical Updates Required:

1. **API Base URLs Update**:
   - Update all `/shops/` calls to `/businesses/`
   - Update all `/barbers/` calls to `/employees/`
   - Update all `/shop-owners/` calls to `/business-owners/`

2. **Request/Response Field Updates**:
   - Replace `shop_id` with `business_id` in all API calls
   - Replace `barber_id` with `employee_id` in all API calls
   - Replace `comments` with `message` in feedback-related calls

3. **Component Naming Updates**:
   - Rename all "Shop" components to "Business"
   - Rename all "Barber" components to "Employee" 
   - Update state variable names throughout the app

4. **Form Field Updates**:
   - Update form field names to match new schema
   - Add support for new fields like `notes`, `total_duration`, `total_price`

5. **New Features to Implement** (Optional):
   - Business advertisements management
   - Contact messages handling
   - Enhanced operating hours with lunch breaks
   - Employee schedule management with day-of-week system

### 📋 Testing Requirements:
- Test all CRUD operations for businesses (formerly shops)
- Test all CRUD operations for employees (formerly barbers)
- Verify appointment booking still works with new field names
- Test queue management functionality
- Verify feedback submission with new message field

### 🆔 New ID Fields Available:
- All responses now include both old and new terminology during transition
- Frontend should migrate to use `business_id` and `employee_id` exclusively
