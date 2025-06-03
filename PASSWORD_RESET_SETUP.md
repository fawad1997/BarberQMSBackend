# Password Reset Setup Guide

## Overview
This guide explains how to set up the password reset functionality that has been implemented.

## Backend Setup

### 1. Install Dependencies
```bash
pip install aiosmtplib emails
```

### 2. Environment Variables
Add the following environment variables to your `.env` file:

```env
# Email Configuration (for password reset)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
FROM_EMAIL=your-email@gmail.com

# Frontend URL (for password reset links)
FRONTEND_URL=http://localhost:3000
```

### 3. Database Migration
Run the following command to add password reset fields to the User model:

```bash
# If migration fails due to chain issues, you can manually add the columns:
# ALTER TABLE users ADD COLUMN reset_token VARCHAR;
# ALTER TABLE users ADD COLUMN reset_token_expires TIMESTAMP WITH TIME ZONE;
# CREATE INDEX ix_users_reset_token ON users(reset_token);

alembic upgrade head
```

### 4. Gmail App Password Setup (if using Gmail)
1. Enable 2-factor authentication on your Gmail account
2. Generate an App Password:
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate a password for "Mail"
   - Use this password as SMTP_PASSWORD

## Frontend Setup

The frontend components have been created and are ready to use:

### New Components Added:
- `components/pages/auth/reset-password-form.tsx` - Password reset form
- `app/reset-password/[token]/page.tsx` - Reset password page
- `app/api/auth/validate-reset-token/route.ts` - Token validation API
- `app/api/auth/reset-password/route.ts` - Password reset API

### Updated Components:
- `app/api/auth/forgot-password/route.ts` - Now calls backend API

## How It Works

1. **Forgot Password Flow:**
   - User enters email on `/forgot-password`
   - Backend generates secure token and saves to database
   - Email is sent with reset link containing token
   - Token expires after 1 hour

2. **Reset Password Flow:**
   - User clicks link in email (goes to `/reset-password/[token]`)
   - Frontend validates token with backend
   - If valid, user can enter new password
   - Backend updates password and clears reset token

3. **Security Features:**
   - Secure token generation using `secrets.token_urlsafe(32)`
   - Token expiration (1 hour)
   - No user enumeration (always returns success for forgot password)
   - Password validation (8+ chars, uppercase, lowercase, number)
   - Tokens are cleared after use or expiration

## API Endpoints

### Backend (FastAPI)
- `POST /auth/forgot-password` - Send reset email
- `POST /auth/validate-reset-token` - Validate reset token
- `POST /auth/reset-password` - Reset password with token

### Frontend (Next.js API Routes)
- `POST /api/auth/forgot-password` - Proxy to backend
- `POST /api/auth/validate-reset-token` - Proxy to backend
- `POST /api/auth/reset-password` - Proxy to backend

## Testing

### Development Mode
If SMTP credentials are not configured, emails will be logged to console instead of sent.

### Production Mode
Ensure all email environment variables are properly configured.

## Troubleshooting

1. **Migration Issues:**
   - If alembic migration fails, manually add the database columns
   - Check database connection and permissions

2. **Email Issues:**
   - Verify SMTP credentials
   - Check firewall/network restrictions
   - For Gmail, ensure App Password is used (not regular password)

3. **Token Issues:**
   - Tokens expire after 1 hour
   - Tokens are single-use (cleared after password reset)
   - Check database for reset_token and reset_token_expires fields

## Files Modified/Added

### Backend Files:
- `requirements.txt` - Added email libraries
- `app/models.py` - Added reset token fields to User model
- `app/schemas.py` - Added password reset schemas
- `app/routers/auth.py` - Added password reset endpoints
- `app/utils/email_service.py` - New email service
- `alembic/versions/b4c5d8019e25_*.py` - Database migration

### Frontend Files:
- `app/reset-password/[token]/page.tsx` - New reset password page
- `components/pages/auth/reset-password-form.tsx` - New reset form component
- `app/api/auth/forgot-password/route.ts` - Updated to call backend
- `app/api/auth/validate-reset-token/route.ts` - New API route
- `app/api/auth/reset-password/route.ts` - New API route 