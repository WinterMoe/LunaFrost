import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.sendgrid.net')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SENDER_EMAIL = os.getenv('SENDER_EMAIL', '')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD', '')
APP_NAME = os.getenv('APP_NAME', 'Novel Translator')
APP_URL = os.getenv('APP_URL', 'http://localhost:5000')

def send_password_reset_email(email, reset_token, user_id):

    if not SENDER_EMAIL or not SENDER_PASSWORD:
        return {'success': False, 'error': 'Email service not configured'}
    
    try:
        reset_link = f"{APP_URL}/auth/reset-password?token={reset_token}"
        
        subject = f"{APP_NAME} - Password Reset Request"
        
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f7fafc; border-radius: 8px;">
                    <div style="text-align: center; margin-bottom: 30px;">
                        <img src="{APP_URL}/static/images/logo_transparent_resized.png" alt="{APP_NAME}" style="max-height: 60px;">
                    </div>
                    
                    <div style="background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h3 style="color: #2d3748; margin-bottom: 20px;">Password Reset Request</h3>
                        
                        <p style="color: #4a5568; line-height: 1.6; margin-bottom: 20px;">
                            We received a request to reset the password for your {APP_NAME} account. 
                            If you did not make this request, you can ignore this email.
                        </p>
                        
                        <p style="color: #4a5568; line-height: 1.6; margin-bottom: 30px;">
                            To reset your password, click the button below. This link will expire in 1 hour.
                        </p>
                        
                        <div style="text-align: center; margin-bottom: 30px;">
                            <a href="{reset_link}" style="background-color: #667eea; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                                Reset Password
                            </a>
                        </div>
                        
                        <p style="color: #718096; font-size: 0.9rem; margin-bottom: 10px;">
                            Or copy and paste this link in your browser:
                        </p>
                        
                        <p style="color: #4299e1; font-size: 0.85rem; word-break: break-all; background-color: #f7fafc; padding: 10px; border-radius: 4px;">
                            {reset_link}
                        </p>
                        
                        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
                        
                        <p style="color: #718096; font-size: 0.85rem; margin-bottom: 10px;">
                            If you did not request a password reset, please ignore this email or contact support if you have concerns.
                        </p>
                        
                        <p style="color: #718096; font-size: 0.85rem;">
                            Best regards,<br>
                            The {APP_NAME} Team
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        text_content = f"""
        {APP_NAME} - Password Reset Request
        
        We received a request to reset the password for your {APP_NAME} account.
        If you did not make this request, you can ignore this email.
        
        To reset your password, visit this link (expires in 1 hour):
        {reset_link}
        
        Or copy and paste this URL in your browser:
        {reset_link}
        
        If you did not request a password reset, please ignore this email or contact support if you have concerns.
        
        Best regards,
        The {APP_NAME} Team
        """
        
        message = MIMEMultipart('alternative')
        message['Subject'] = subject
        message['From'] = SENDER_EMAIL
        message['To'] = email
        
        message.attach(MIMEText(text_content, 'plain'))
        message.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login('apikey', SENDER_PASSWORD)
            server.send_message(message)
        
        return {'success': True, 'message': 'Reset email sent successfully'}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': f'Failed to send email: {str(e)}'}

def send_welcome_email(email, username):

    if not SENDER_EMAIL or not SENDER_PASSWORD:
        return {'success': False, 'error': 'Email service not configured'}
    
    try:
        subject = f"Welcome to {APP_NAME}!"
        
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f7fafc; border-radius: 8px;">
                    <h2 style="color: #667eea; text-align: center; margin-bottom: 30px;">📚 {APP_NAME}</h2>
                    
                    <div style="background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h3 style="color: #2d3748; margin-bottom: 20px;">Welcome, {username}!</h3>
                        
                        <p style="color: #4a5568; line-height: 1.6; margin-bottom: 20px;">
                            Thank you for signing up for {APP_NAME}. Your account is ready to use!
                        </p>
                        
                        <p style="color: #4a5568; line-height: 1.6; margin-bottom: 20px;">
                            You can now:
                        </p>
                        
                        <ul style="color: #4a5568; line-height: 1.8; margin-bottom: 20px;">
                            <li>Import novels using our browser extension</li>
                            <li>Translate chapters with AI</li>
                            <li>Manage your character glossary</li>
                            <li>Export novels as PDF or EPUB</li>
                            <li>Customize your settings and preferences</li>
                        </ul>
                        
                        <div style="text-align: center; margin-bottom: 30px;">
                            <a href="{APP_URL}" style="background-color: #667eea; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                                Get Started
                            </a>
                        </div>
                        
                        <p style="color: #718096; font-size: 0.85rem;">
                            If you have any questions, feel free to contact our support team.
                        </p>
                        
                        <p style="color: #718096; font-size: 0.85rem;">
                            Best regards,<br>
                            The {APP_NAME} Team
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        text_content = f"""
        Welcome to {APP_NAME}, {username}!
        
        Thank you for signing up for {APP_NAME}. Your account is ready to use!
        
        You can now:
        - Import novels using our browser extension
        - Translate chapters with AI
        - Manage your character glossary
        - Export novels as PDF or EPUB
        - Customize your settings and preferences
        
        Get started: {APP_URL}
        
        If you have any questions, feel free to contact our support team.
        
        Best regards,
        The {APP_NAME} Team
        """
        
        message = MIMEMultipart('alternative')
        message['Subject'] = subject
        message['From'] = SENDER_EMAIL
        message['To'] = email
        
        message.attach(MIMEText(text_content, 'plain'))
        message.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login('apikey', SENDER_PASSWORD)
            server.send_message(message)
        
        return {'success': True, 'message': 'Welcome email sent'}
        
    except Exception as e:
        return {'success': False, 'error': f'Failed to send email: {str(e)}'}

def send_email_change_confirmation(email, username):

    if not SENDER_EMAIL or not SENDER_PASSWORD:
        return {'success': False, 'error': 'Email service not configured'}
    
    try:
        subject = f"{APP_NAME} - Email Address Changed"
        
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f7fafc; border-radius: 8px;">
                    <h2 style="color: #667eea; text-align: center; margin-bottom: 30px;">📚 {APP_NAME}</h2>
                    
                    <div style="background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h3 style="color: #2d3748; margin-bottom: 20px;">Email Address Updated</h3>
                        
                        <p style="color: #4a5568; line-height: 1.6; margin-bottom: 20px;">
                            Your email address for {APP_NAME} has been successfully updated to this email address.
                        </p>
                        
                        <p style="color: #4a5568; line-height: 1.6; margin-bottom: 20px;">
                            If you did not make this change, please contact our support team immediately.
                        </p>
                        
                        <p style="color: #718096; font-size: 0.85rem;">
                            Best regards,<br>
                            The {APP_NAME} Team
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        text_content = f"""
        {APP_NAME} - Email Address Updated
        
        Your email address for {APP_NAME} has been successfully updated to this email address.
        
        If you did not make this change, please contact our support team immediately.
        
        Best regards,
        The {APP_NAME} Team
        """
        
        message = MIMEMultipart('alternative')
        message['Subject'] = subject
        message['From'] = SENDER_EMAIL
        message['To'] = email
        
        message.attach(MIMEText(text_content, 'plain'))
        message.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login('apikey', SENDER_PASSWORD)
            server.send_message(message)
        
        return {'success': True}
        
    except Exception as e:
        return {'success': False}

def send_contact_email(name, user_email, topic, message_text):

    if not SENDER_EMAIL or not SENDER_PASSWORD:
        return {'success': False, 'error': 'Email service not configured'}
    
    try:
        target_email = "contact@lunafrost.moe"
        subject = f"{APP_NAME} Contact: {topic} - {name or 'Anonymous'}"
        
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f7fafc; border-radius: 8px;">
                    <h2 style="color: #667eea; text-align: center; margin-bottom: 30px;">📬 New Contact Message</h2>
                    
                    <div style="background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <div style="margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid #e2e8f0;">
                            <p><strong>From:</strong> {name or 'Anonymous'} ({user_email})</p>
                            <p><strong>Topic:</strong> {topic}</p>
                        </div>
                        
                        <h3 style="color: #2d3748; margin-bottom: 15px;">Message:</h3>
                        <div style="background-color: #f7fafc; padding: 15px; border-radius: 4px; white-space: pre-wrap; color: #4a5568;">
                            {message_text}
                        </div>
                        
                        <p style="color: #718096; font-size: 0.85rem; margin-top: 30px;">
                            This email was sent from the {APP_NAME} contact form.
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        text_content = f"""
        New Contact Message from {APP_NAME}
        
        From: {name or 'Anonymous'} ({user_email})
        Topic: {topic}
        
        Message:
        {message_text}
        """
        
        message = MIMEMultipart('alternative')
        message['Subject'] = subject
        message['From'] = SENDER_EMAIL
        message['To'] = target_email
        message['Reply-To'] = user_email
        
        message.attach(MIMEText(text_content, 'plain'))
        message.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login('apikey', SENDER_PASSWORD)
            server.send_message(message)
        
        return {'success': True}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': f'Failed to send email: {str(e)}'}