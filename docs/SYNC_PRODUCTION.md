# مزامنة قاعدة البيانات مع PythonAnywhere

هذا الدليل يشرح كيف تنقل بياناتك المحلية إلى الموقع المنشور على
PythonAnywhere بأمان، وكيف تتجنب فقدان البيانات أثناء تحديث الكود.

## مكان قاعدة البيانات

التطبيق يقرأ قاعدة البيانات من المتغير `DATABASE` في `config.py`:

```python
DATABASE = os.environ.get('DATABASE') or os.path.join(basedir, 'database', 'data.db')
```

- **محلياً:** `database/data.db`
- **على PythonAnywhere:** نفس المسار داخل مجلد المشروع (`database/data.db`)

> **مهم:** قاعدة البيانات **لا تُرفع عبر Git**. هذا مقصود ويبقى كذلك
> (`*.db` مستثناة في `.gitignore`). GitHub ينقل الكود فقط، والبيانات
> تُنقل بالطريقة أدناه.

## تهيئة قاعدة بيانات جديدة (تحذير — مدمر!)

أمر قسري hazard تنفيذه دون فهمه:

```
python -m flask --app app.py init-db --confirm
```

`--confirm` في هذا المشروع يعني **حذف البيانات الحالية وإعادة التهيئة** من
`database/schema.sql`. لا تشغّله إذا كانت القاعدة تحتوي بيانات، فهو يدمّرها
وليس مجرد فحص. عند بدء التشغيل يقوم التطبيق تلقائياً بـ `ensure_schema()`
لتطبيق الـ migrations المطلوبة دون مسح المستخدمين.

## نقل بياناتك المحلية إلى PythonAnywhere

> نفّذ هذه الخطوات مرة واحدة بعد أن تتأكد من البيانات المحلية، وكرّرها
> كلما أردت تحديث بيانات الموقع من جهازك.

### 1) خذ نسخة احتياطية من القاعدة الحية (اختياري ولكن يُنصح)

```powershell
python scripts/backup_db.py
```

ينشئ نسخة متسقة (لقطة SQLite Backup API) في `database/backups/`.

### 2) جهّز ملف الرفع

أفضل طريقة لإنتاج لقطة نظيفة (تتجاهل ملفات WAL/SHM): استخدم أداة النسخ الموجودة:

```powershell
python scripts/backup_db.py
```

الملف الناتج باسم `data-YYYYMMDD-HHMMSS.db` هو ملف قاعدة صالح للرفع.
يمكنك أيضاً نسخه لمسار ثابت:

```powershell
Copy-Item database\backups\data-*.db database\backups\data-for-pythonanywhere.db
```

**قبل الرفع تحقق من الملف الناتج:**

```powershell
python -c "import sqlite3; c=sqlite3.connect('database/backups/data-for-pythonanywhere.db'); print(c.execute('PRAGMA integrity_check').fetchone()[0]); print('users:', c.execute('SELECT COUNT(*) FROM users').fetchone()[0])"
```

يجب أن تُطبع `ok` وأن يظهر عدد المستخدمين المتوقع.

### 3) الرفع إلى PythonAnywhere

1. سجّل الدخول إلى [PythonAnywhere](https://www.pythonanywhere.com).
2. تبويب **Files** → انتقل إلى مجلد `database/` داخل مشروعك.
3. **أولاً احفظ نسخة القاعدة الموجودة** على الموقع (حمّلها لجهازك أو
   أعد تسميتها إلى `data.db.prod-backup.db`).
4. احذف أي ملفات `data.db-wal` أو `data.db-shm` قديمة إن وُجدت في نفس المجلد.
5. ارفع الملف `data-for-pythonanywhere.db` من جهازك (زر **Upload**)
   ثم أعد تسميته ليحل محل `data.db`.
6. تبويب **Web** → زّر **Reload**.

### 4) التحقق

سجّل الدخول على الموقع بحساب تعرفه (مثال: `admin` أو أي رئيس قسم) وتأكد
من دخول البيانات. لو ظهرت أخطاء، استعد نسخة `data.db.prod-backup.db`.

## نموذج العمل (تحديث الكود لا يمس البيانات)

```
            GitHub (كود فقط)
                  │
          ┌───────┴───────┐
          ↓               ↓
      جهازك           PythonAnywhere
   بيانات محلية        بيانات الموقع
```

- تعديل الكود → `git push` → على PythonAnywhere `git pull` + **Reload**
  (لا يُمسّ أي شيء في البيانات).
- تعديل البيانات محلياً للموقع → اتبع خطوات النقل في القسم السابق.

## الحسابات الرؤساء (كلمة المرور `123123`)

| الاسم | المستخدم | الدور |
|---|---|---|
| أمالة المالطي | `amal` | رئيس قسم الحاسوب |
| الهام ابوالشواشي | `ilham` | مدير مكتب أعضاء هيئة التدريس |
| حنان معمر | `hanan` | رئيس قسم العمارة |
| ياسر جرافة | `yasser` | رئيس قسم المدني |
| مراد الفنطازي | `murad` | رئيس قسم النفط |
| فوزي ابوالشواشي | `fawzi` | رئيس قسم الاتصالات |
| غالية المالطي | `ghaliya` | رئيس قسم البحث والتطوير والمناهج |
| عبدالرؤوف غريبة | `abdo` | رئيس قسم الدراسة والامتحانات |