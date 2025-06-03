import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("FROM_EMAIL", self.smtp_username)
        self.backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
        self.frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        
    def send_password_reset_email(self, to_email: str, reset_token: str, user_name: str) -> bool:
        """Send password reset email to user"""
        try:
            # Create reset link using backend-served page
            reset_link = f"{self.backend_url}/auth/reset-password?token={reset_token}"
            
            # Create email content
            subject = "Password Reset Request - BarberQMS"
            
            html_body = f"""
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
                        If the button doesn't work, you can copy and paste this link into your browser:
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
            
            text_body = f"""
            Password Reset Request
            
            Hello {user_name},
            
            We received a request to reset your password for your BarberQMS account.
            If you didn't make this request, you can safely ignore this email.
            
            To reset your password, visit this link:
            {reset_link}
            
            This link will expire in 1 hour for security reasons.
            
            Best regards,
            The BarberQMS Team
            """
            
            return self._send_email(to_email, subject, html_body, text_body)
            
        except Exception as e:
            logger.error(f"Error sending password reset email: {str(e)}")
            return False
    
    def _send_email(self, to_email: str, subject: str, html_body: str, text_body: str) -> bool:
        """Send email using SMTP"""
        try:
            if not self.smtp_username or not self.smtp_password:
                logger.warning("SMTP credentials not configured, email not sent")
                # In development, just log the email content
                logger.info(f"Would send email to {to_email} with subject: {subject}")
                logger.info(f"Email content: {text_body}")
                return True
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = to_email
            
            # Create text and HTML parts
            text_part = MIMEText(text_body, 'plain')
            html_part = MIMEText(html_body, 'html')
            
            # Add parts to message
            msg.attach(text_part)
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Password reset email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return False

# Global email service instance
email_service = EmailService() 