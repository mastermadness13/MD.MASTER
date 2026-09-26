# GUIDES_MAP.md

يُقرأ هذا الملف **بدل** محاولة قراءة كل `github-pages-main` (4005 ملف،
288 ميجا — معظمه غير ذي صلة). كل جلسة تعمل على مجال من
`AUDIT_TRACKER.md` تفتح فقط الأدلة المطابقة له أدناه، لا غير.

> **جميع المسارات أدناه نسبية لمجلد `_audit_guides/` داخل المشروع** — وهي
> مطابقة حرفياً لما كانت عليه داخل الأرشيف، فبقيت أعمدة "المسار" صالحة
> دون تعديل. مجلد `_audit_guides/` هو 285 ملف / 1.43 ميجا.

---

## خريطة الربط بمجالات AUDIT_TRACKER.md

### P0 §7 — المصادقة والتفويض

| المصدر | المسار داخل `_audit_guides/` | ملاحظة |
|---|---|---|
| Cloudflare security-audit-skill | `security-audit-skill-main/skills/security-audit/WEB-PROTOCOL-AND-AUTH.md` | مباشر — أنماط هجوم بروتوكول HTTP والمصادقة |
| Cloudflare security-audit-skill | `security-audit-skill-main/skills/security-audit/SKILL.md` | مبادئ عامة + "أنماط تدقيق خاطئة" يجب تجنبها |

### P0 §8 — الدفاع الأمني العام (XSS, CSRF, حقن، إعدادات)

| المصدر | المسار | ملاحظة |
|---|---|---|
| Claude Skills | `skills-main/security-best-practices/SKILL.md` | يدعم Python صراحةً — الأنسب لمراجعة الكود مباشرة |
| Claude Skills | `skills-main/security-threat-model/SKILL.md` | منهجية "حدود الثقة + مسارات إساءة الاستخدام" — مفيدة لخريطة الأدوار التسعة بمشروعك |
| Cloudflare security-audit-skill | `security-audit-skill-main/skills/security-audit/CLIENT-SIDE.md` | حقن DOM، ثقة الرسائل — يخص قوالب Jinja2 + JS |
| Cloudflare security-audit-skill | `security-audit-skill-main/skills/security-audit/ATTACK-CLASSES.md` | فئات هجوم أساسية عامة |

### P0 §9 — أمان منطق الأعمال (IDOR بين الأقسام/الأدوار)

| المصدر | المسار | ملاحظة |
|---|---|---|
| Cloudflare security-audit-skill | `security-audit-skill-main/skills/security-audit/DATA-ISOLATION-AND-LIFECYCLE.md` | **الأكثر صلة بمشكلتك تحديداً** — عزل البيانات بين المستأجرين/الأدوار، يطابق تماماً سؤال "هل معلم قسم يقدر يوصل لبيانات قسم ثاني؟" |

### P0 §10 — أمان رفع الملفات

لا يوجد دليل مخصص كافٍ بالأرشيف لهذا تحديداً — استخدم القسم 10 بالبرومبت
الأصلي مباشرة (هو مفصّل بذاته: امتداد، MIME، مسار، تسمية آمنة).

### P1 §5/§6 — Backend وقاعدة البيانات (مبادئ عامة)

| المصدر | المسار | ملاحظة |
|---|---|---|
| Claude Skills | `senior-backend-dev-master/senior-backend-dev-master/SKILL.md` | عام (Node/Python/Java/Go/Rust) — طبّق المبدأ، تجاهل أمثلة اللغات الثانية |
| Claude Skills (Supabase) | `skills-main/postgres-best-practices/` | مبادئ الفهرسة/الاستعلامات تنتقل جزئياً لـ SQLite — **تجاهل** أي بنية SQL خاصة بـ Postgres فقط (RLS, extensions) |

### مرجعي فقط (كود حقيقي، ليس نثراً — لا يُقرأ بالكامل، يُرجع له عند الحاجة)

| المصدر | المسار | متى تفتحه |
|---|---|---|
| مستودع Flask نفسه | `FLASK-main/src/flask/` | لو احتجت تفهم سلوك داخلي محدد (مثلاً توقيع جلسة الكوكيز في `sessions.py`، أو `app.py`/`sansio/app.py`) |
| مشروع تعليمي REST+Flask | `rest-apis-flask-python-develop/project/` | لو احتجت مرجع لهيكلة Blueprints/Migrations — يستخدم SQLAlchemy لا SQLite الخام، فالنقل يحتاج تكييف |

---

## استُبعد كلياً — ولماذا

| المصدر | سبب الاستبعاد |
|---|---|
| `skill-security-reviewer-main` | **فخ:** يفحص أمان المهارات (Skills) نفسها كملفات مثبَّتة، لا أمان تطبيقات الويب. غير ذي علاقة إطلاقاً بـ §8 رغم الاسم المشابه |
| كل مهارات Kotlin/Spring (`schema-migration-planner`, `test-suite-builder`, `error-model-validation-architect`, `transaction-consistency-designer`, وغيرها) | تقنية مختلفة كلياً (Kotlin+Spring)، لا علاقة بـ Flask/Python |
| كل مهارات Vue (`vue`, `vue-best-practices`, `pinia`, `nuxt`, إلخ) | مشروعك يستخدم Jinja2 + JS عادي، لا Vue |
| `gws-*` (Google Workspace)، `notion-*` | غير ذي صلة |
| `*-deploy` (netlify, vercel, render, cloudflare) | تُنشر على PythonAnywhere، لا هذي المنصات |
| `awesome-sqlite-master` | قائمة روابط خارجية فقط، مو محتوى مباشر قابل للتطبيق |
| `python-skills-main` | موجّه لنشر مكتبات Python على PyPI، لا لتطبيق ويب |
| باقي مجلدات `skills-main` (~90 مجلد إضافي) | تصميم، ألعاب، أدوات نشر منصات ثانية — لا صلة |

---

## ما قُصِد استبعاده داخل `FLASK-main` تحديداً

الأصل كان 317 ملف / **131 ميجا**، لكن 125 ميجا منها مجلد
`gpt_review/outputs/*.jsonl` — مخرجات تقييم نماذج LLM (bard/llama2/vicuna/gpt4)
لا علاقة لها بسلوك Flask إطلاقاً. لذلك نُسخ منه فقط:

- `FLASK-main/src/flask/` — 26 ملف / 340KB (المصدر الفعلي، وهو المطلوب)
- `FLASK-main/docs/` — 87 ملف / 784KB (مرجع سلوكي)

وتُركت بدون نسخ: `gpt_review/`، `evaluation_set/`، `input_data/`،
`model_output/`، `openai_info/`، `metadata_annotation/`، `tests/`،
`examples/`، ومجلدات `__pycache__` المتسربة.

---

## كيف يُستخدم هذا مع بقية الملفات

بأول رسالة لأي جلسة جديدة (بعد الرسالة الثابتة من `CONTINUATION_PROTOCOL.md`)،
أضف سطر واحد:

```
عند فتح أي دليل خارجي، استخدم GUIDES_MAP.md فقط لتحديد المسار — لا تتصفح
مجلد github-pages-main الكامل.
```
