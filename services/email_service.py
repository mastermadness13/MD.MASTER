import smtplib
import logging
import html
import json
import os
from urllib import error as urllib_error
from urllib import request as urllib_request
from email.mime.text import MIMEText
from config import Config

logger = logging.getLogger(__name__)
BREVO_API_URL = 'https://api.brevo.com/v3/smtp/email'


def _brevo_sender_config():
    """Return the configured Brevo sender, or None to use the SMTP fallback."""
    api_key = os.environ.get('BREVO_API_KEY')
    sender_email = os.environ.get('BREVO_SENDER_EMAIL')
    if not api_key or not sender_email:
        return None
    return api_key, sender_email, os.environ.get('BREVO_SENDER_NAME', 'ROPEY')


def _send_brevo_email(to_email: str, recipient_name: str, subject: str,
                      text_body: str, html_body: str) -> bool:
    config = _brevo_sender_config()
    if not config:
        return False
    api_key, sender_email, sender_name = config
    payload = json.dumps({
        'sender': {'name': sender_name, 'email': sender_email},
        'to': [{'email': to_email, 'name': recipient_name or to_email}],
        'subject': subject,
        'textContent': text_body,
        'htmlContent': html_body,
    }).encode('utf-8')
    req = urllib_request.Request(
        BREVO_API_URL,
        data=payload,
        headers={
            'api-key': api_key,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib_request.urlopen(req, timeout=10) as response:
            return 200 <= response.status < 300
    except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError, OSError):
        logger.exception('Failed to send email through Brevo to %s', to_email)
        return False


# /     /     >---- إرسال بريد إعادة تعيين كلمة المرور للمستخدم
def send_reset_email(to_email: str, reset_url: str) -> bool:
    try:
        subject = 'إعادة تعيين كلمة المرور - كلية التقنية الهندسية زوارة'
        body = (
            'مرحباً،\n\n'
            'تلقينا طلباً لإعادة تعيين كلمة المرور لحسابك في بوابة كلية التقنية الهندسية زوارة.\n\n'
            f'رابط إعادة تعيين كلمة المرور:\n{reset_url}\n\n'
            'هذا الرابط صالح لمدة ساعة واحدة فقط.\n\n'
            'إذا لم تطلب إعادة تعيين كلمة المرور، يرجى تجاهل هذه الرسالة.\n\n'
            'مع التحية،\n'
            'فريق الدعم الفني - كلية التقنية الهندسية زوارة'
        )

        # /     /     >---- تجهيز الرسالة بتنسيق نص بسيط وترميز عربي
        msg = MIMEText(body, _charset='utf-8')
        msg['Subject'] = subject
        msg['From'] = Config.MAIL_DEFAULT_SENDER
        msg['To'] = to_email

        # /     /     >---- الاتصال بخادم البريد مع تشفير TLS وتسجيل الدخول
        with smtplib.SMTP(Config.MAIL_SERVER, Config.MAIL_PORT, timeout=10) as server:
            server.starttls()
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            server.send_message(msg)

        logger.info(f'Reset email sent to {to_email}')
        return True
    except Exception as e:
        logger.error(f'Failed to send reset email to {to_email}: {e}')
        return False


# /     /     >---- إرسال رمز الدخول الأولي لعضو هيئة التدريس (بريده الخاص فقط)
def send_initial_login_code(
    to_email: str,
    username: str,
    code: str,
    expiry_days: int,
    *,
    renewed: bool = False,
) -> bool:
    try:
        subject = (
            'تجديد رمز الدخول - بوابة كلية التقنية الهندسية زوارة'
            if renewed else
            'رمز الدخول الأولي - بوابة كلية التقنية الهندسية زوارة'
        )
        intro = (
            'تم تجديد رمز الدخول الخاص بحسابك بناءً على طلب إدارة النظام.'
            if renewed else
            'تم إنشاء حسابك في بوابة كلية التقنية الهندسية زوارة.'
        )
        body = (
            'مرحباً بك في بوابة كلية التقنية الهندسية زوارة.\n\n'
            f'{intro}\n\n'
            f'نيك نيم (اسم الدخول): {username}\n'
            f'رمز الدخول المؤقت: {code}\n\n' if renewed else
            'مرحباً بك في بوابة كلية التقنية الهندسية زوارة.\n\n'
            f'{intro}\n\n'
            f'نيك نيم (اسم الدخول): {username}\n'
            f'رمز الدخول المؤقت: {code}\n\n'
        ) + (
            f'يرجى تسجيل الدخول بهذا الرمز خلال {expiry_days} أيام؛ '
            'بعد أول تسجيل دخول يجب تعيين كلمة مرور خاصة بك من صفحة الأمان.\n\n'
            'هذه الرسالة وُجّهت إلى بريدك الشخصي ويحتفظ مكتب أعضاء هيئة التدريس بنسخة من الرمز لإيصالها لك عند الحاجة.\n\n'
            'أهلاً بك في المجتمع الأكاديمي،\n'
            'مكتب إدارة أعضاء هيئة التدريس'
        )

        html_body = (
            '<div dir="rtl" style="font-family:sans-serif">'
            f'<p>مرحباً {html.escape(username)}،</p>'
            f'<p>{html.escape(intro)}</p>'
            f'<p><strong>نيك نيم:</strong> {html.escape(username)}<br>'
            f'<strong>رمز الدخول المؤقت:</strong> {html.escape(code)}</p>'
            f'<p>يرجى استخدام الرمز خلال {expiry_days} أيام، ثم تعيين كلمة مرور جديدة.</p>'
            '</div>'
        )
        if _brevo_sender_config() and _send_brevo_email(
                to_email, username, subject, body, html_body):
            logger.info('Initial login code email sent through Brevo to %s', to_email)
            return True
        if _brevo_sender_config():
            return False

        msg = MIMEText(body, _charset='utf-8')
        msg['Subject'] = subject
        msg['From'] = Config.MAIL_DEFAULT_SENDER
        msg['To'] = to_email

        with smtplib.SMTP(Config.MAIL_SERVER, Config.MAIL_PORT, timeout=10) as server:
            server.starttls()
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            server.send_message(msg)

        logger.info(f'Initial login code email sent to {to_email}')
        return True
    except Exception as e:
        logger.error(f'Failed to send initial login code to {to_email}: {e}')
        return False


def send_test_email(to_email: str, recipient_name: str = '') -> bool:
    """Send a harmless delivery test using the configured mail transport."""
    subject = 'اختبار البريد الإلكتروني - بوابة كلية التقنية الهندسية زوارة'
    greeting = recipient_name or to_email
    body = (
        f'مرحباً {greeting}،\n\n'
        'هذه رسالة اختبار من بوابة كلية التقنية الهندسية زوارة.\n'
        'إذا وصلت هذه الرسالة، فإن إعداد البريد يعمل بشكل صحيح.\n\n'
        'هذه الرسالة لا تغيّر كلمة المرور ولا بيانات الحساب.\n'
    )
    html_body = (
        '<div dir="rtl" style="font-family:sans-serif">'
        f'<p>مرحباً {html.escape(greeting)}،</p>'
        '<p>هذه رسالة اختبار من بوابة كلية التقنية الهندسية زوارة.</p>'
        '<p>إذا وصلت هذه الرسالة، فإن إعداد البريد يعمل بشكل صحيح.</p>'
        '<p>هذه الرسالة لا تغيّر كلمة المرور ولا بيانات الحساب.</p>'
        '</div>'
    )
    try:
        if _brevo_sender_config():
            return _send_brevo_email(
                to_email, recipient_name, subject, body, html_body
            )
        msg = MIMEText(body, _charset='utf-8')
        msg['Subject'] = subject
        msg['From'] = Config.MAIL_DEFAULT_SENDER
        msg['To'] = to_email
        with smtplib.SMTP(Config.MAIL_SERVER, Config.MAIL_PORT, timeout=10) as server:
            server.starttls()
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            server.send_message(msg)
        logger.info('Test email sent to %s', to_email)
        return True
    except (smtplib.SMTPException, OSError, TimeoutError) as exc:
        logger.error('Failed to send test email to %s: %s', to_email, exc)
        return False