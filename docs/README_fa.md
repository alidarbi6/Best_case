# Best Case Workflow — نسخهٔ پایتون

تبدیل کامل ورک‌فلو KNIME (`best_case.knwf`) و سند «Drilling Operations Best Case Workflow» به پایتون.
هدف: شناسایی خودکار بهترین زمان و بهترین عملکرد عملیات حفاری در چاه‌های حفاری‌شده، و استخراج پارامترهای حفاری متناظر.

## ساختار

```
config/
  settings.yaml          تنظیمات اصلی (اتصال، انتخاب دیتابیس، پارامترهای هر مرحله، خروجی)
  rules.yaml             قوانین پاک‌سازی/نگاشت (با همان سینتکس Rule Engine و String Manipulation کی‌نایم)
  lookups.yaml           لیست چاه‌های طراحی جدید و جدول‌های نگاشت (code1→activity، opscategory→operation)
  queries/
    queries.yaml         فهرست کوئری‌ها + ستون‌های مورد انتظار هر کدام + برنامهٔ اجرا در هر حالت
    system/databases.sql
    per_table/*.sql      یک SELECT برای هر جدول (مثل ورک‌فلو؛ join در pandas)
    sql_join/*.sql       کوئری‌های join نسخهٔ اول سند
    sql_full/*.sql       کوئری‌های تجمیعی نسخهٔ جدید سند
src/best_case/
  engine/                بلوک‌های عمومی معادل نودهای KNIME (Joiner, GroupBy, Duplicate Row Filter, Sorter, Rule Engine, ...)
  io/                    منبع داده (SQL Server / پوشهٔ CSV)، رجیستری کوئری
  stages/                مراحل خط لوله (هر مرحله یک فایل)
  pipeline.py cli.py     ترتیب مراحل و خط فرمان
  testing/synthetic.py   داده ساختگی برای تست و اجرای بدون دیتابیس
tests/                   تست‌های واحد و انتها‌به‌انتها
```

## نصب و اجرا

```bash
pip install -e .[mssql,test]          # یا: pip install -r requirements.txt
export BEST_CASE_DB_PASSWORD='...'    # رمز هرگز در کد/فایل تنظیمات نیست
export BEST_CASE_DB_USER='sa'         # اختیاری (پیش‌فرض: database.user)
python -m best_case run --settings config/settings.yaml
```

گزینه‌های مفید:

| دستور | کار |
|---|---|
| `--set queries.mode=per_table` | SELECT تک‌جدولی و join در pandas (رفتار ورک‌فلو) |
| `--set source.type=csv_dir` | اجرا از روی فایل‌های CSV (بدون دیتابیس) |
| `--only start_end --only sections` | فقط مراحل مشخص |
| `--cache-dir .cache --from-stage sections` | ذخیرهٔ خروجی هر مرحله و ادامه از یک مرحله |
| `python -m best_case stages` | فهرست مراحل |
| `python -m best_case demo-data --out data/raw` | ساخت داده ساختگی |

اجرای بدون دیتابیس: `demo-data` سپس `run --set source.type=csv_dir` (خروجی در `output/`).

## مراحل و نگاشت به نودهای KNIME

| مرحله | فایل | نودهای KNIME | بخش سند |
|---|---|---|---|
| extract | `stages/extract.py` | #376 #379 #380 #377 #402 + نودهای DB + Joinerهای #452 #429 #430 #453 #405 #440 #446 #438 + Loop End #400 | 1، 1.1، 1.2، 1.3 |
| time_log | `stages/time_log.py` | #413 #412 #539 + پاک‌سازی (#410 #371 #372 #375 #373 #381 #415 #411 #416) | 1.2 |
| start_end | `stages/start_end.py` | زیرگردش START/END (#651) | «به‌روزرسانی dttmend_time/dttmstart_time» |
| formations | `stages/formations.py` | #542 #576 #574 #575 #577 #578 #474 #475 #513 #532 #537 #663 | 1.4 |
| drilling_parameters | `stages/drilling_parameters.py` | #540 #495 #497 #683 #684 #526 | 1.3 |
| formation_split | `stages/formation_split.py` | #502 #544 #525 #545 #567 #566 #621 #551 | 2 |
| merge_time_log | `stages/merge_time_log.py` | #658 #659 #660 #664 #665 #667 #668 #669 | 2 |
| sections | `stages/sections.py` | #369 زیرگردش COMPLETED HO (#398) #460 #397 #439 | 2 |
| best_case | `stages/best_case.py` | #186 #233 #234 #676 #681 #686 (+فیلترهای آزمایشی) | 2 |
| approaches | `stages/approaches.py` | Approach 1/2/3 (#454 #456 #464) #374 #414 #383 | — (فقط در ورک‌فلو) |
| export | `stages/export.py` | Excel Writer #687 | — |

## گزارش مقایسه (هم‌قالب پاورپوینت «Best Case Demo»)

مرحلهٔ `report` بعد از اجرای اصلی، در `output/report/` می‌سازد:

* `best_case_report.xlsx` — هر شیت معادل یک اسلاید با **همان عنوان ستون‌ها** + نمودار واقعی اکسل:

| شیت | اسلاید | ستون‌ها |
|---|---|---|
| `6 Approach I - Duration by Well` | ۶ | Hole Section، یک ستون برای هر چاه (روز) + نمودار |
| `7 Approach I vs II` | ۷ | Hole Section, Approach I, Approach II + نمودار |
| `8 Comparison` | ۸ | Hole Section, Approach I, Approach II, Approach Combination, ردیف Total |
| `9 Duration - All Approaches` | ۹ | همان + نمودار |
| `11 Duration by Formation` | ۱۱ | Hole Section, Well, Type, Formation, Duration (Days) |
| `12 Min Duration by Formation` | ۱۲ | همان ستون‌ها |
| `13 Drilling Parameters I` | ۱۳ | Hole Section, Well, Date, Formation, Duration (Hours), Drilling Parameters (DDRs) |
| `14 Drilling Parameters II` | ۱۴ | Record, Hole Section, Well, Date, Formation, Parameter, Value |

* تصاویر PNG: `slide06…`, `slide07…`, `slide09…`, `slide14_drilling_parameters.png` و سه نمودار اضافه
  (`extra_heatmap_well_vs_section` نقشهٔ حرارتی همهٔ چاه‌ها × بخش‌ها، `extra_best_well_by_formation` سهم هر سازند در بهترین چاه هر بخش، `extra_min_by_well_type` مقایسهٔ JR و SPH).

تعریف‌ها (اسلاید ۴): **Approach I** = کمینهٔ جمع کل مدت هر چاه در هر بخش؛ **Approach II** = جمع کمینهٔ هر فعالیت (`code1`) در هر بخش؛
**Approach Combination** = کمتر از دو مقدار بالا. ستون‌های Best Case (New Design/Combination) اسلاید ۸ طبق توضیح شما از منبع دیگری است و ساخته نمی‌شود.

تنظیمات در `settings.yaml` بخش `report:`: `wells` (فهرست چاه‌ها، پیش‌فرض همه)، `hole_sections` (پیش‌فرض 24, 17, 12 1/4, 8 1/2 مثل اسلایدها؛ خالی = همه)،
`ddr.comment_pattern` (کدام توضیحات به‌عنوان DDR نشان داده شود؛ پیش‌فرض `*param*`)، `parameters` و `example` (اسلاید ۱۴).
نمودار خوشه‌ای حداکثر `max_series` چاه را نشان می‌دهد؛ نقشهٔ حرارتی همیشه همهٔ چاه‌ها را دارد.
غیرفعال کردن: `--set report.enabled=false`.

## تغییر کوئری‌ها

1. **ویرایش یک کوئری**: فایل `.sql` مربوطه را عوض کنید. فقط شرط: نام ستون‌های خروجی همانی باشد که در `queries.yaml` زیر `columns:` آمده (در صورت تغییر نام از `AS` استفاده کنید). اگر ستونی کم باشد، برنامه دقیقاً می‌گوید کدام کوئری و کدام ستون.
2. **افزودن/تعویض فایل**: در `queries.yaml` مقدار `file:` را عوض کنید.
3. **حالت اجرا** (`queries.mode`):
   * `per_table` — ۱۰ SELECT جداگانه، joinها در pandas (رفتار ورک‌فلو).
   * `sql_join` — سه کوئری join نسخهٔ اول سند (`job_rig`, `report_timelog`, `drillstring_joined`)؛ بقیهٔ joinها در pandas.
   * `sql_full` (**پیش‌فرض**، نسخهٔ جدید سند) — دو کوئری تجمیعی `time_log_full` و `drill_full` (همه‌چیز شامل wellname/jobtyp/des در SQL Server) + `formation`. کوئری `general_well_data` سند هم در `sql_full/` هست ولی join آن داخل دو کوئری بالا آمده و جداگانه خوانده نمی‌شود.
   هر سه حالت در تست‌ها نتیجهٔ یکسان می‌دهند (`tests/test_pipeline.py`). استخراج تاریخ/ساعت و ضرب `duration×24` همچنان در پایتون انجام می‌شود.
4. نام دیتابیس‌ها در `database_selection` (الگوهای wildcard) تنظیم می‌شود؛ جدول‌ها داخل هر دیتابیس خوانده می‌شوند.

## تغییر قوانین پاک‌سازی

همه در `config/rules.yaml` هستند. هر قانون همان سینتکس KNIME است، مثلاً:

```yaml
- '$code4$ LIKE "*12*1/4*" => "12 1/4"'
- 'TRUE => $code4$'
```

پشتیبانی‌شده: `=  !=  <  <=  >  >=  LIKE  MATCHES  IN  AND  OR  NOT  MISSING  TRUE/FALSE`، توابع
`strip lowerCase upperCase replaceChars capitalize replace substr join floor ceil round abs if min max ...`.
اولین قانونِ برقرار برنده است؛ مقایسه با مقدار گمشده نادرست است؛ `LIKE` حساس به حروف است.
لیست چاه‌های طراحی جدید و جدول‌های نگاشت approachها در `lookups.yaml` است.

## تعویض یک مرحله

در `settings.yaml`:

```yaml
pipeline:
  overrides:
    start_end: my_package.my_module:my_function   # تابعی با امضای fn(ctx)
```
تابع از `ctx.tables[...]` می‌خواند و خروجی‌های همان مرحله را در `ctx.tables` می‌نویسد.

## فیلترهای آزمایشی ورک‌فلو (پیش‌فرض خاموش)

در ورک‌فلو چند فیلتر ثابت (SPH-15 / code4=17 / aghajari / *wob* / category=sph) روی مسیر نتیجه هست که ظاهراً برای آزمایش بوده‌اند.
در `settings.yaml` زیر `best_case.post_filters` با `enabled: false` آمده‌اند؛ برای فعال‌سازی `true` کنید.
مسیر فایل Excel (در ورک‌فلو `C:\Users\...\test.xlsx`) در `export.excel.file` و `export.directory` تنظیم می‌شود.

## تست

```bash
python -m pytest -q          # ۳۷ تست؛ نیازی به دیتابیس ندارد
```
تست‌ها شامل: موتور قانون/عبارت، Joiner، GroupBy، Duplicate Row Filter، Sorter، هر مرحله، اجرای کامل روی داده ساختگی،
و اجرای هر دو حالت کوئری روی SQLite با همان فایل‌های `.sql`.

## تفاوت‌ها، فرض‌ها و موارد مبهم (لطفاً بازبینی شود)

**فیلتر چاه‌ها (مهم):** نود Rule-based Row Splitter (#412) در KNIME روی «Exclude TRUE matches» است، یعنی ورک‌فلو چاه‌هایی را پردازش می‌کند که *در لیست `lookups.yaml` نیستند* (تأییدشده توسط کاربر). تنظیم: `time_log.well_filter_mode: exclude | include`.

**آنچه در ورک‌فلو هست و در سند نیست** — پیاده‌سازی شده: تبدیل `duration × 24`، START/END، COMPLETED HO، سه Approach، خروجی Excel.

**فرض‌هایی که از روی تنظیمات نودها استنباط شد:**

1. **Moving Aggregator (START/END)** در ورک‌فلو با `cumulative=true` و `window=forward` تنظیم شده؛ چون منطق گره (جمع تجمعی از اولین فعالیت روز تا فعالیت جاری و شرط ۲۴ ساعت) با جمع تجمعی از ابتدای روز سازگار است، پیش‌فرض `start_end.cumulative: backward` (جمع از اول روز) است. اگر در KNIME خروجی متفاوت دیدید `forward` (جمع از ردیف جاری تا آخر روز) را امتحان کنید. **این مورد را حتماً با خروجی KNIME تطبیق دهید.**
2. `convert to int` در Math Formula: گرد کردن (`round`). گزینهٔ `start_end.minutes_to_int: trunc` موجود است.
3. مقایسهٔ مقدار گمشده در فیلترها/قوانین همیشه *نادرست* است (حتی `NEQ`)؛ در Joiner کلید گمشده با کلید گمشده match نمی‌شود.
4. COMPLETED HO: ترتیب «طبیعی» (natural) روی `code4`؛ برای چاه بدون `completion` اولین ردیف (کوچک‌ترین قطر) حذف می‌شود.
5. GroupBy/Concatenate: جداکننده `", "`، مقدار گمشده `?`، و اعداد صحیح‌مقدار بدون `.0` چاپ می‌شوند (نوع دقیق ستون در KNIME ممکن است `12.0` بدهد).
6. ترتیب ردیف‌های خروجی GroupBy در KNIME نامشخص است؛ اینجا ترتیب اولین ظهور (و برای formations بر اساس `form_seq`).
7. در ورک‌فلو نودهای زیر به جایی وصل نیستند و پیاده نشدند: #592 (فیلتر SPH-15/gachsaran)، #679 و #401/#370/#408 (Math/Constant انتهای approachها)، #395 (نگاشت چاه→formation)، #581، #688. خروجی approachها به‌صورت شیت `approaches` و CSV ذخیره می‌شود.
8. در زیرگردش‌های Approach ستونی به نام `formation` استفاده شده که در جریان اصلی `formname` است؛ با `approaches.formation_column` تنظیم می‌شود (پیش‌فرض `formname`).
9. فیلتر `category = sph` (#673) در ورک‌فلو حساس به حروف نیست ولی مقدار واقعی `SPH` است؛ فعال‌سازی آن با مقدار `sph` و `case_sensitive: false` بدون مشکل کار می‌کند.
10. دسترسی به SQL Server در محیط توسعه نبود؛ منطق با داده ساختگی و SQLite تست شد. **پیشنهاد:** یک بار خروجی را با خروجی KNIME روی همان داده مقایسه کنید (`--cache-dir` مقادیر میانی هر مرحله را برای مقایسه با پورت‌های KNIME ذخیره می‌کند).
