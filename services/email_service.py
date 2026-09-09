import smtplib
import logging
from email.mime.text import MIMEText
from config import Config

logger = logging.getLogger(__name__)


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

        msg = MIMEText(body, _charset='utf-8')
        msg['Subject'] = subject
        msg['From'] = Config.MAIL_DEFAULT_SENDER
        msg['To'] = to_email

        with smtplib.SMTP(Config.MAIL_SERVER, Config.MAIL_PORT, timeout=10) as server:
            server.starttls()
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            server.send_message(msg)

        logger.info(f'Reset email sent to {to_email}')
        return True
    except Exception as e:
        logger.error(f'Failed to send reset email to {to_email}: {e}')
        return False
