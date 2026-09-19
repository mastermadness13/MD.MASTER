"""Upload policy constants."""

# /     /     >---- الحجم الأقصى للملفات المرفوعة: 16 ميجابايت
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

# /     /     >---- الصيغ المسموح رفعها
ALLOWED_UPLOAD_EXTENSIONS = {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx',
                             'jpg', 'jpeg', 'png', 'gif', 'zip', 'rar', 'txt',
                             'csv', 'mp4', 'mp3'}