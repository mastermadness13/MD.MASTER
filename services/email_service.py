import smtplib
import logging
from email.mime.text import MIMEText
from config import Config

logger = logging.getLogger(__name__)


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
            'بعد أول تسجيل دخول يمكنك تغيير الرمز من صفحة الأمان أو الاحتفاظ به.\n\n'
            'هذه الرسالة وُجّهت إلى بريدك الشخصي ويحتفظ مكتب أعضاء هيئة التدريس بنسخة من الرمز لإيصالها لك عند الحاجة.\n\n'
            'أهلاً بك في المجتمع الأكاديمي،\n'
            'مكتب إدارة أعضاء هيئة التدريس'
        )

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