# Production Email Setup Guide

## 🚀 Setting Up Real Email Sending for Password Reset

### Option A: Gmail Setup (Quick & Easy)

#### Step 1: Enable 2-Factor Authentication
1. Go to [Google Account Settings](https://myaccount.google.com/)
2. Click "Security" in the left sidebar
3. Under "Signing in to Google", click "2-Step Verification"
4. Follow the setup process to enable 2FA

#### Step 2: Generate App Password
1. Still in Security settings, click "2-Step Verification"
2. Scroll down and click "App passwords"
3. Select "Mail" from the dropdown
4. Click "Generate"
5. **Copy the 16-character password** (e.g., `abcd efgh ijkl mnop`)

#### Step 3: Update Your .env File
Add these variables to your `.env` file in the backend:

```env
# Gmail SMTP Configuration
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=abcd efgh ijkl mnop
FROM_EMAIL=your-email@gmail.com

# Frontend URL (update for production)
FRONTEND_URL=http://localhost:3000
```

#### Step 4: Test the Setup
1. Restart your backend server
2. Try the forgot password flow
3. Check that you receive the email

---

### Option B: SendGrid Setup (Recommended for Production)

#### Step 1: Create SendGrid Account
1. Go to [SendGrid](https://sendgrid.com/)
2. Sign up for free account (100 emails/day free)
3. Verify your email address

#### Step 2: Create API Key
1. In SendGrid dashboard, go to Settings → API Keys
2. Click "Create API Key"
3. Choose "Restricted Access"
4. Give it a name like "BarberQMS Password Reset"
5. Under "Mail Send", select "Full Access"
6. Click "Create & View"
7. **Copy the API key** (starts with `SG.`)

#### Step 3: Verify Sender Identity
1. Go to Settings → Sender Authentication
2. Click "Verify a Single Sender"
3. Fill in your details (use your business email)
4. Check your email and click the verification link

#### Step 4: Update Backend Code for SendGrid

Create a new email service for SendGrid:

```python
# app/utils/sendgrid_service.py
import os
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

logger = logging.getLogger(__name__)

class SendGridEmailService:
    def __init__(self):
        self.api_key = os.getenv("SENDGRID_API_KEY")
        self.from_email = os.getenv("FROM_EMAIL")
        self.frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        
    def send_password_reset_email(self, to_email: str, reset_token: str, user_name: str) -> bool:
        try:
            if not self.api_key:
                logger.warning("SendGrid API key not configured")
                return False
                
            # Create reset link
            reset_link = f"{self.frontend_url}/reset-password/{reset_token}"
            
            # Create email content (same HTML as before)
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Password Reset</title>
            </head>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0; font-size: 28px;">Password Reset Request</h1>
                </div>
                
                <div style="background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; border: 1px solid #ddd;">
                    <p style="font-size: 16px; margin-bottom: 20px;">Hello {user_name},</p>
                    
                    <p style="font-size: 16px; margin-bottom: 20px;">
                        We received a request to reset your password for your BarberQMS account. 
                        If you didn't make this request, you can safely ignore this email.
                    </p>
                    
                    <p style="font-size: 16px; margin-bottom: 30px;">
                        To reset your password, click the button below:
                    </p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{reset_link}" 
                           style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                  color: white; 
                                  padding: 15px 30px; 
                                  text-decoration: none; 
                                  border-radius: 5px; 
                                  font-weight: bold; 
                                  font-size: 16px; 
                                  display: inline-block;">
                            Reset Password
                        </a>
                    </div>
                    
                    <p style="font-size: 14px; color: #666; margin-top: 30px;">
                        If the button doesn't work, copy and paste this link into your browser:
                    </p>
                    <p style="font-size: 14px; color: #667eea; word-break: break-all;">
                        {reset_link}
                    </p>
                    
                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd;">
                        <p style="font-size: 14px; color: #666; margin: 0;">
                            This link will expire in 1 hour for security reasons.
                        </p>
                        <p style="font-size: 14px; color: #666; margin: 10px 0 0 0;">
                            Best regards,<br>
                            The BarberQMS Team
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            message = Mail(
                from_email=self.from_email,
                to_emails=to_email,
                subject="Password Reset Request - BarberQMS",
                html_content=html_content
            )
            
            sg = SendGridAPIClient(api_key=self.api_key)
            response = sg.send(message)
            
            logger.info(f"Password reset email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email via SendGrid: {str(e)}")
            return False

# Global instance
sendgrid_service = SendGridEmailService()
```

#### Step 5: Update Environment Variables for SendGrid

```env
# SendGrid Configuration
SENDGRID_API_KEY=SG.your-api-key-here
FROM_EMAIL=your-verified-email@yourdomain.com
FRONTEND_URL=https://yourdomain.com
```

#### Step 6: Install SendGrid Package

```bash
pip install sendgrid
```

#### Step 7: Update requirements.txt

Add to your requirements.txt:
```
sendgrid==6.10.0
```

---

## 🔧 Quick Setup Instructions

### For Gmail (Fastest):
1. Enable 2FA on your Gmail account
2. Generate App Password
3. Add these to your `.env`:
   ```env
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your-email@gmail.com
   SMTP_PASSWORD=your-16-char-app-password
   FROM_EMAIL=your-email@gmail.com
   FRONTEND_URL=http://localhost:3000
   ```
4. Restart backend server
5. Test forgot password flow

### For SendGrid (Production):
1. Create SendGrid account
2. Generate API key
3. Verify sender email
4. Install: `pip install sendgrid`
5. Add to `.env`:
   ```env
   SENDGRID_API_KEY=SG.your-api-key
   FROM_EMAIL=your-verified-email@domain.com
   FRONTEND_URL=https://yourdomain.com
   ```
6. Update email service to use SendGrid
7. Test the flow

---

## 🚨 Important Security Notes

1. **Never commit .env files** to version control
2. **Use environment variables** in production
3. **Verify sender domains** for better deliverability
4. **Monitor email sending** for abuse
5. **Set up SPF/DKIM records** for your domain

---

## 📊 Testing Checklist

- [ ] User receives password reset email
- [ ] Email contains working reset link
- [ ] Reset link expires after 1 hour
- [ ] Password is successfully updated
- [ ] User can login with new password
- [ ] Old reset tokens don't work
- [ ] Email design looks professional

---

## 🆘 Troubleshooting

### Gmail Issues:
- Make sure 2FA is enabled
- Use App Password, not regular password
- Check "Less secure app access" is OFF
- Verify SMTP settings are correct

### SendGrid Issues:
- Verify sender identity is confirmed
- Check API key permissions
- Monitor SendGrid dashboard for delivery status
- Ensure FROM_EMAIL matches verified sender

### General Issues:
- Check firewall/network restrictions
- Verify environment variables are loaded
- Check server logs for detailed errors
- Test with different email providers 