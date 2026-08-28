<div align="center">

# Arabic RTL Processor — معالج النصوص العربية للطرفيات

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Cython](https://img.shields.io/badge/Cython-3.0%2B-003B5C?style=for-the-badge&logo=cython&logoColor=white)](https://cython.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

**معالج نصوص عربية فائق السرعة معتمد على Cython و 1BRC للعرض المتصل والصحيح في الطرفيات الموجهة من اليسار إلى اليمين (LTR).**

**A blazing-fast, Cython-powered Arabic text processor engineered with 1BRC techniques for seamless connected cursive display in Left-to-Right (LTR) terminals.**

<br/>

[**العربية**](#arabic--العربية) | [**English**](#english)

</div>

---

## Arabic / العربية

أداة ومعالِج نصوص عربية فائق السرعة مصمم للطرفيات وبيئات سطر الأوامر (CLI) مثل Windows Terminal و [Ghostty](https://ghostty.org/) و Alacritty و Kitty و Foot والتي لا تدعم عرض النصوص من اليمين إلى اليسار (RTL) بشكل صحيح. يعتمد المشروع على **[Cython](https://cython.org)** ويستفيد من تقنيات تحسين الأداء المستوحاة من تحدي **"[1 Billion Row Challenge (1BRC)](https://github.com/ifnesi/1brc)"** و **"[py-1brc](https://github.com/benhoyt/py-1brc)"** للوصول إلى سرعة معالجة تتجاوز ملايين الأحرف في الثانية مع تشكيل متصل سلس.

### طريقة العمل

يقوم البرنامج بتشكيل الحروف العربية سياقياً (Presentation Forms-B) وعكس اتجاه الكلمات والجمل لتعرض بشكل متصل وصحيح في الطرفيات:

1. **التشكيل السياقي التلقائي (Contextual Cursive Shaping):** دمج الحروف بأشكالها المتصلة (بداية، وسط، نهاية، منفصل) وحل تراكيب اللام-ألف ولفظ الجلالة (ﷲ).
2. **عكس ترتيب الكلمات** في السطر مع الحفاظ على الأرقام والنصوص الإنجليزية من اليسار إلى اليمين (LTR).
3. **تجاوز ذكي تلقائي** لكل مما يلي:
   - النصوص الإنجليزية والأرقام والتواريخ والنسب المئوية
   - الكتل البرمجية (``` ... ```) والأكواد المضمنة (`code`)
   - الروابط (http://, https://, ftp://)
   - مسارات الملفات (/path/to/file, ~/path, C:\path)
   - أوامر Shell ($ or # at start) وبوادئ Markdown (- [ ], >, 1.)

<div align="left" dir="ltr">

```text
Original:
السلام عليكم ورحمة الله
# hi
filepath:/home/user/work
print("Hello world")

Output:
ﷲ ﺔﻤﺣﺭﻭ ﻢﻜﻴﻠﻋ ﻡﻼﺴﻟﺍ
# hi
filepath:/home/user/work
print("Hello world")
```

</div>

### المميزات الأساسية

- **سرعة فائقة (1BRC-Engine):** معالجة ملايين الأسطر في أجزاء من الثانية بفضل C-Extensions، و OpenMP والتجميع الأصيل AVX2.
- **تشكيل عربي متصل 100%:** تشكيل سياقي كامل (Unicode Presentation Forms-B) يلغي الفراغات المتقطعة بين الحروف.
- **Zero LLM Tokens:** معالجة سريعة محلياً دون الحاجة لاستهلاك Tokens عبر واجهات الذكاء الاصطناعي.
- **مخرجات نظيفة تماماً:** إخراج النصوص مباشرة إلى stdout بدون أي رسائل إحصائية افتراضية.
- **واجهة سطر أوامر (CLI) شاملة:** تدعم إدخال النصوص مباشرة، التمرير عبر الأنابيب (Piping)، ومعالجة الملفات الكبيرة باستخدام الذاكرة المشتركة `mmap`.
- **واجهة برمجة تطبيقات (Python API):** سهلة الاستخدام والدمج المباشر داخل مشاريع Python.
- **تكامل مع عملاء الذكاء الاصطناعي:** توفير مهارة ([opencode](https://opencode.ai) & Antigravity Skill) جاهزة للاستخدام التلقائي.

---

### بنية التطوير والأداء (1BRC Techniques)

- **معالجة مكدس الذاكرة (100% C Stack Allocation):** تنفيذ التجزئة والتشكيل والعكس في C دون أي تخصيص في الذاكرة الديناميكية (Zero heap/malloc) مع `nogil`.
- **جداول البحث النقطية 64-بت (64-bit Bitmaps):** فحص محارف اليونيكود العربية والتشكيل بزمن ثابت $O(1)$ عبر تعليمات المعالج المباشرة.
- **إنشاء نصوص Python مباشرة (PyUnicode C-API):** استخدام `PyUnicode_FromKindAndData` لبناء النتائج في استدعاء C واحد دون كائنات وسيطة.
- **قراءة الملفات عبر `mmap`:** للوصول المباشر إلى الذاكرة دون الحاجة لنسخ محتوى الملفات (Zero-copy).
- **التوازي المفتوح والتجميع الأصيل:** دعم OpenMP و `-O3 -march=native -ffast-math -flto -funroll-loops`.

---

### التثبيت والإعداد

<div align="left" dir="ltr">

```bash
# استنساخ المستودع
git clone https://github.com/BaselCS/arabic-rtl-processor.git
cd arabic-rtl-processor

# التثبيت السريع عبر سكربت التثبيت (يستخدم uv تلقائياً)
bash install.sh
```

أو يدوياً بواسطة `uv`:

```bash
uv venv
source .venv/bin/activate
uv pip install cython setuptools
uv run python setup.py build_ext --inplace
```

</div>

---

### طريقة الاستخدام

#### 1. عبر سطر الأوامر (CLI)

<div align="left" dir="ltr">

```bash
# معالجة نص مباشر
arabic-rtl "السلام عليكم ورحمة الله"

# التمرير عبر الأنابيب (Piping)
echo "بسم الله الرحمن الرحيم" | arabic-rtl
arabic-rtl <<< "الحمد لله رب العالمين"

# معالجة ملف
arabic-rtl -f document.md

# حفظ المخرجات في ملف
arabic-rtl -f input.txt -o output.txt

# معالجة ملف كبير بالتوازي عبر أنوية المعالج
arabic-rtl -f large.txt -t 8

# عرض إحصائيات الأداء والسرعة
arabic-rtl -f document.md -s

# وضع البث المباشر (للأنابيب وسجلات log / tail -f)
tail -f app.log | arabic-rtl --stream
```

</div>

#### 2. عبر مكتبة Python (API)

<div align="left" dir="ltr">

```python
import arabic_rtl

# معالجة النص العربي
text = "السلام عليكم ورحمة الله"
result = arabic_rtl.process_text(text)
print(result)  # ﷲ ﺔﻤﺣﺭﻭ ﻢﻜﻴﻠﻋ ﻡﻼﺴﻟﺍ

# التحقق من وجود حروف عربية
if arabic_rtl.has_arabic("Hello مرحبا"):
    print("تم اكتشاف نص عربي!")

# معالجة متوازية لنصوص ضخمة
result_parallel = arabic_rtl.process_text_parallel(large_text, num_threads=8)
```

</div>

---

### التكامل مع عملاء الذكاء الاصطناعي (AI Skills)

تأتي الأداة مزودة بمهارة `SKILL.md` جاهزة للاندماج مع [opencode](https://opencode.ai) و Antigravity:

<div align="left" dir="ltr">

```bash
# تثبيت المهارة لـ opencode
mkdir -p ~/.opencode/skills/arabic-rtl
cp SKILL.md ~/.opencode/skills/arabic-rtl/

# تثبيت المهارة لـ Antigravity
mkdir -p ~/.gemini/config/skills/arabic-rtl
cp SKILL.md ~/.gemini/config/skills/arabic-rtl/
```

</div>

---

### شكر وتقدير (Acknowledgments)

شكر خاص للمشاريع الملهمة التي اعتمدنا على تقنياتها وأفكارها في تحسين الأداء:
- **[1BRC Challenge (ifnesi/1brc)](https://github.com/ifnesi/1brc):** تحدي الـ 1 Billion Row Challenge الملهم لتقنيات تحسين الأداء وتجاوز حدود السرعة.
- **[py-1brc (Ben Hoyt)](https://github.com/benhoyt/py-1brc):** مشروع Ben Hoyt المميز واستراتيجياته في تحسين أداء Python إلى أقصى سرعة ممكنة.

### الترخيص

هذا المشروع مرخص تحت رخصة [MIT](LICENSE).

---

## English

### Arabic RTL Processor

A high-performance Arabic text processing engine designed for command-line interfaces (CLI) and terminals like Windows Terminal, [Ghostty](https://ghostty.org/), Alacritty, Kitty, and Foot that lack native Right-to-Left (RTL) text rendering support. Powered by **[Cython](https://cython.org)** and leveraging optimization techniques inspired by the **"[1 Billion Row Challenge](https://github.com/ifnesi/1brc)"** and **"[py-1brc](https://github.com/benhoyt/py-1brc)"**, it achieves processing speeds exceeding millions of characters per second with seamless connected cursive shaping.

### How It Works

Transforms Arabic text for correct visual ordering and connected cursive display in Left-to-Right environments:

1. **Contextual Cursive Shaping (Presentation Forms-B):** Shapes letters into their contextual forms (Initial, Medial, Final, Isolated) and resolves Lam-Alef and Allah (ﷲ) ligatures.
2. **Reverses word order** across the line while keeping numbers and English text in LTR order.
3. **Smart auto-skipping** for:
   - English text, numbers, dates, and percentages
   - Code blocks (``` ... ```) and inline code (`code`)
   - URLs (http://, https://, ftp://)
   - File paths (/path/to/file, ~/path, C:\path)
   - Shell commands ($ or # at start) and Markdown prefixes (-, >, 1.)

<div align="left" dir="ltr">

```text
Original:
السلام عليكم ورحمة الله
# hi
filepath:/home/user/work
print("Hello world")

Output:
ﷲ ﺔﻤﺣﺭﻭ ﻢﻜﻴﻠﻋ ﻡﻼﺴﻟﺍ
# hi
filepath:/home/user/work
print("Hello world")
```

</div>

### Key Features

- **Blazing Speed (1BRC-Engine):** Processes millions of lines in milliseconds powered by C-Extensions, OpenMP, and native AVX2 instructions.
- **100% Connected Cursive Shaping:** Full Unicode Presentation Forms-B contextual shaping eliminates broken letter gaps.
- **Zero LLM Tokens:** Fast local processing without burning API tokens when using AI coding assistants.
- **Completely Clean Output:** Transformed text is output directly to stdout with zero unwanted banners or stats.
- **Comprehensive CLI:** Supports direct string input, pipeline stdin piping, and memory-mapped file processing (`mmap`).
- **Clean Python API:** Simple and intuitive library functions for direct integration into Python applications.
- **AI Assistant Integration:** Pre-configured skill (`SKILL.md`) for instant integration with AI agents like opencode and Antigravity.

---

### Architecture & Performance (1BRC Techniques)

- **100% C Stack Allocation:** Token parsing, shaping, and reversal execute inside C stack buffers with `nogil` (zero heap allocations).
- **64-bit Bitmaps (`uint64_t`):** O(1) single-cycle bitwise character and diacritic classification.
- **Direct PyUnicode C-API:** Fast string creation via `PyUnicode_FromKindAndData` without intermediate Python objects.
- **Memory-Mapped I/O (`mmap`):** Direct zero-copy memory access for efficient handling of large files.
- **OpenMP & Native Tuning:** Built with `-O3 -march=native -ffast-math -flto -funroll-loops -fopenmp`.

---

### Installation & Setup

```bash
# Clone the repository
git clone https://github.com/BaselCS/arabic-rtl-processor.git
cd arabic-rtl-processor

# Quick install via installer script (uses uv automatically)
bash install.sh
```

Or manually via `uv`:

```bash
uv venv
source .venv/bin/activate
uv pip install cython setuptools
uv run python setup.py build_ext --inplace
```

---

### Usage

#### 1. Command-Line Interface (CLI)

```bash
# Process direct text input
arabic-rtl "السلام عليكم ورحمة الله"

# Pipe input via stdin
echo "بسم الله الرحمن الرحيم" | arabic-rtl
arabic-rtl <<< "الحمد لله رب العالمين"

# Process a file
arabic-rtl -f document.md

# Save output to file
arabic-rtl -f input.txt -o output.txt

# Multithreaded parallel file processing
arabic-rtl -f large.txt -t 8

# Show performance stats
arabic-rtl -f document.md -s

# Stream mode (for logs / tail -f)
tail -f app.log | arabic-rtl --stream
```

#### 2. Python API

```python
import arabic_rtl

# Process Arabic text
text = "السلام عليكم ورحمة الله"
result = arabic_rtl.process_text(text)
print(result)  # ﷲ ﺔﻤﺣﺭﻭ ﻢﻜﻴﻠﻋ ﻡﻼﺴﻟﺍ

# Check if text contains Arabic characters
if arabic_rtl.has_arabic("Hello مرحبا"):
    print("Arabic text detected!")

# Parallel processing for large texts
result_parallel = arabic_rtl.process_text_parallel(large_text, num_threads=8)
```

---

### AI Assistant Integration (Skills)

Integrate this tool as a skill with [opencode](https://opencode.ai) or Antigravity:

```bash
# Install skill for opencode
mkdir -p ~/.opencode/skills/arabic-rtl
cp SKILL.md ~/.opencode/skills/arabic-rtl/

# Install skill for Antigravity
mkdir -p ~/.gemini/config/skills/arabic-rtl
cp SKILL.md ~/.gemini/config/skills/arabic-rtl/
```

---

### Acknowledgments

Special thanks to the inspiring projects and creators whose performance techniques contributed to this project:
- **[1BRC Challenge (ifnesi/1brc)](https://github.com/ifnesi/1brc):** The 1 Billion Row Challenge that inspired high-performance optimization techniques.
- **[py-1brc (Ben Hoyt)](https://github.com/benhoyt/py-1brc):** Ben Hoyt's excellent repository on pushing Python performance to its extreme limits.

### License

This project is licensed under the [MIT License](LICENSE).

