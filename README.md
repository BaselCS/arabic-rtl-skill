<div align="center">

# Arabic RTL Processor — معالج النصوص العربية للطرفيات

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Cython](https://img.shields.io/badge/Cython-3.0%2B-003B5C?style=for-the-badge&logo=cython&logoColor=white)](https://cython.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

**معالج نصوص عربية عالي الأداء معتمد على Cython للعرض الصحيح في الطرفيات الموجهة من اليسار إلى اليمين (LTR).**

**A blazing-fast, Cython-powered Arabic text processor for correct display in Left-to-Right (LTR) terminals.**

<br/>

<a href="sample.png"><img src="sample.png" width="600" alt="Terminal Processing Preview"/></a>

<br/>

[**العربية**](#arabic--العربية) | [**English**](#english)

</div>

---

## Arabic / العربية

أداة ومعالِج نصوص عربية عالي السرعة مصمم للطرفيات وبيئات سطر الأوامر (CLI) مثل Windows Terminal و [Ghostty](https://ghostty.org/) والتي لا تدعم عرض النصوص من اليمين إلى اليسار (RTL) بشكل صحيح. يعتمد المشروع على **[Cython](https://cython.org)** ويستفيد من تقنيات تحسين الأداء المستوحاة من تحدي **"[1 Billion Row Challenge](https://1brc.dev/)"** للوصول إلى سرعة معالجة تتجاوز مليون سطر في الثانية.

### طريقة العمل

يقوم البرنامج بتحويل النص العربي ليعرض بشكل صحيح في الطرفيات ذات الاتجاه من اليسار إلى اليمين عبر خطوتين:
1. **عكس ترتيب الحروف** داخل كل كلمة عربية.
2. **عكس ترتيب الكلمات** في السطر بالكامل.

ما يتجاوزه:
- النصوص الانجليزية والأرقام
- الكتل البرمجية (``` ... ```)
- الروابط (http://, https://, ftp://)
- المسارات (file:///path/to/file, ~/path)
- أوامر Shell ($ or # at start)

<div align="left" dir="ltr">

```text
الأصل :
السلام عليكم ورحمة الله
# hi
filepath:/home/user/work
print("Hello world")

المرسل :
هللا ةمحرو مكيلع مالسلا
# hi
filepath:/home/user/work
print("Hello world")
```

</div>

### المميزات الأساسية

* **سرعة فائقة:** معالجة أكثر من مليون سطر في الثانية بفضل C-Extensions و Cython.
* **Zero LLM Tokens:** معالجة سريعة محلياً دون الحاجة لاستهلاك Tokens عبر واجهات الذكاء الاصطناعي.
* **واجهة سطر أوامر (CLI) مرنة:** تدعم إدخال النصوص مباشرة، التمرير عبر الأنابيب (Piping)، ومعالجة الملفات الكبيرة باستخدام خيوط متعددة.
* **واجهة برمجة تطبيقات (Python API):** سهلة الاستخدام والدمج المباشر داخل مشاريع Python.
* **تكامل مع عملاء الذكاء الاصطناعي:** توفير أداة ومكون (Skill) جاهز للاستخدام الفوري مع عملاء الذكاء الاصطناعي مثل opencode.
* **تغطية شاملة لترميز اليونيكود العربي:** تشمل دعم كتل Arabic، و Arabic Supplement، و Extended-A، و Presentation Forms A & B.

---

### بنية التطوير

بنيت هذه الأداة لتعمل بكفاءة فائقة وسرعة استثنائية، مع التركيز على التقنيات التالية:
* **استخدام Cython لتجميع امتداد أصيل (Native Extension):** مجمّع باستخدام الخيارات `-O3 -march=native` لأقصى سرعة ممكنة.
* **جدول البحث النقطي (Bitmap Lookup Table):** فحص محارف اليونيكود العربية بزمن ثابت $O(1)$ وبحجم ذاكرة لا يتجاوز 8KB.
* **قراءة الملفات عبر `mmap`:** للوصول المباشر إلى الذاكرة دون الحاجة لنسخ محتوى الملفات الكبيرة (Zero-copy memory access).
* **المعالجة متعددة الخيوط (Multiprocessing):** لدعم خيوط معالجة متعددة، وتجاوز قفل GIL، وتفعيل التوازي الفعلي.
* **إلغاء فحص الحدود (`boundscheck=False`):** لتقليل تكلفة الفحص البرمجي وضمان أقصى سرعة تنفيذية.

### التقنيات المستخدمة

* **اللغة الأساسية:** [Python 3.10+](https://python.org)
* **المسارع والمجمّع:** [Cython 3.0+](https://cython.org) (مع C Compiler / GCC)
* **تقنيات الذاكرة والتوازي:** `mmap`, `multiprocessing.Pool`
* **إدارة الحزم والمشاريع:** `uv`, `setuptools`

---

### التثبيت والإعداد

<div align="left" dir="ltr">

```bash
# استنساخ المستودع
git clone https://github.com/BaselCS/arabic-rtl-processor.git
cd arabic-rtl-processor

# إنشاء وتفعيل بيئة افتراضية بواسطة uv
uv venv
source .venv/bin/activate

# تثبيت الاعتمادات وبناء الامتداد الأصيل (Native Extension)
uv pip install cython setuptools
uv run python setup.py build_ext --inplace
```

</div>

### طريقة الاستخدام

#### 1. عبر سطر الأوامر (CLI)

<div align="left" dir="ltr">

```bash
# معالجة نص مباشر
python3 arabic_rtl_cli.py "السلام عليكم ورحمة الله"

# التمرير عبر الأنابيب (Piping)
echo "بسم الله الرحمن الرحيم" | python3 arabic_rtl_cli.py

# معالجة ملف (تستخدم mmap للملفات الكبيرة)
python3 arabic_rtl_cli.py --file input.txt

# معالجة ملف بخيوط متعددة (Multithreaded)
python3 arabic_rtl_cli.py --file large.txt --threads 4

# حفظ المخرجات في ملف
python3 arabic_rtl_cli.py --file input.txt --output output.txt

# الوضع الهادئ (بدون عرض الإحصائيات)
echo "Hello مرحبا" | python3 arabic_rtl_cli.py --quiet

# تشغيل اختبار الأداء (Benchmark)
python3 arabic_rtl_cli.py --benchmark
```

</div>

#### 2. عبر مكتبة Python (API)

<div align="left" dir="ltr">

```python
from arabic_rtl import reverse_arabic_text, has_arabic

# معالجة النص
result = reverse_arabic_text("الحمد لله رب العالمين")
print(result)  # نيملاعلا بر هلل دمحلا

# التحقق من وجود حروف عربية
if has_arabic("Hello مرحبا"):
    print("تم اكتشاف نص عربي!")
```

</div>

### التكامل مع opencode

يمكن استخدام هذه الأداة كمهارة ([opencode Skill](https://opencode.ai)). قم بنسخ ملف `SKILL.md` إلى مجلد مهارات opencode لديك:

<div align="left" dir="ltr">

```bash
mkdir -p ~/.opencode/skills/arabic-rtl
cp SKILL.md ~/.opencode/skills/arabic-rtl/
```

</div>

### المتطلبات

* Python 3.10 أو أحدث
* Cython 3.0 أو أحدث
* GCC / Clang (لتجميع الامتداد البرمجي)

### شكر وتقدير (Acknowledgments)

شكر خاص للمشاريع الملهمة التي اعتمدنا على تقنياتها وأفكارها في تحسين الأداء:
* **[1BRC Challenge (ifnesi/1brc)](https://github.com/ifnesi/1brc):** تحدي الـ 1 Billion Row Challenge الملهم لتقنيات تحسين الأداء وتجاوز حدود السرعة.
* **[py-1brc (Ben Hoyt)](https://github.com/benhoyt/py-1brc):** مشروع Ben Hoyt المميز واستراتيجياته في تحسين أداء Python إلى أقصى سرعة ممكنة.

### المساهمة

المساهمات البرمجية والاقتراحات مرحب بها دائماً. يمكنك فتح Issue أو إرسال Pull Request للمساهمة في تطوير وتحسين المشروع.

### الترخيص

هذا المشروع مرخص تحت رخصة [MIT](LICENSE).

---

## English

### Arabic RTL Processor

A high-performance Arabic text processing tool designed for command-line interfaces (CLI) and terminals like Windows Terminal and [Ghostty](https://ghostty.org/) that lack native Right-to-Left (RTL) text rendering support. Powered by **[Cython](https://cython.org)** and leveraging optimization techniques inspired by the **"[1 Billion Row Challenge](https://1brc.dev/)"**, it achieves processing speeds exceeding 1,000,000 lines per second.

### How It Works

Transforms Arabic text for correct visual ordering in Left-to-Right environments through a 2-step process:
1. **Reverses character order** within each Arabic word.
2. **Reverses word order** across the entire line.

Skips all English text, numbers, and the following:

```text
Original: 
السلام عليكم ورحمة الله
# hi
filepath:/home/user/work
print("Hello world")

output:
هللا ةمحرو مكيلع مالسلا
# hi
filepath:/home/user/work
print("Hello world")

```

### Key Features

* **Blazing Speed:** Processes over 1 million lines per second powered by C-Extensions and Cython.
* **Zero LLM Tokens:** Fast local processing without burning API tokens when using AI coding assistants.
* **Flexible CLI Interface:** Supports direct string input, pipeline input piping, file processing, and multi-core multithreading.
* **Clean Python API:** Simple and intuitive library functions for direct integration into Python applications.
* **AI Assistant Integration:** Pre-configured skill (`SKILL.md`) for instant integration with AI agents like opencode.
* **Comprehensive Unicode Coverage:** Supports Standard Arabic, Arabic Supplement, Extended-A, and Presentation Forms A & B blocks.

---

### Architecture & Performance

Engineered for extreme performance and ultra-low latency using the following techniques:
* **Compiled Cython Native Extension:** Built with `-O3 -march=native` compiler flags for maximum execution speed.
* **Bitmap Lookup Table:** $O(1)$ Arabic character detection requiring only an 8KB memory footprint.
* **Memory-Mapped I/O (`mmap`):** Direct zero-copy memory access for efficient handling of large files.
* **True Parallelism (`multiprocessing`):** Multi-threaded execution bypasses Python's GIL for full multi-core utilization.
* **Disabled Bounds Checking (`boundscheck=False`):** Eliminates index checking overhead to maximize execution speed.

### Tech Stack

* **Core Language:** [Python 3.10+](https://python.org)
* **Compiler & Accelerator:** [Cython 3.0+](https://cython.org) (with GCC / C Compiler)
* **Concurrency & Memory:** `mmap`, `multiprocessing.Pool`
* **Package Management:** `uv`, `setuptools`

---

### Installation & Setup

```bash
# Clone the repository
git clone https://github.com/BaselCS/arabic-rtl-processor.git
cd arabic-rtl-processor

# Create and activate virtual environment via uv
uv venv
source .venv/bin/activate

# Install dependencies and build native extension
uv pip install cython setuptools
uv run python setup.py build_ext --inplace
```

### Usage

#### 1. Command-Line Interface (CLI)

```bash
# Process direct text input
python3 arabic_rtl_cli.py "السلام عليكم ورحمة الله"

# Pipe input via stdin
echo "بسم الله الرحمن الرحيم" | python3 arabic_rtl_cli.py

# Process a file (uses mmap for large files)
python3 arabic_rtl_cli.py --file input.txt

# Multithreaded file processing
python3 arabic_rtl_cli.py --file large.txt --threads 4

# Save output to file
python3 arabic_rtl_cli.py --file input.txt --output output.txt

# Quiet mode (suppress performance statistics)
echo "Hello مرحبا" | python3 arabic_rtl_cli.py --quiet

# Run performance benchmark suite
python3 arabic_rtl_cli.py --benchmark
```

#### 2. Python API

```python
from arabic_rtl import reverse_arabic_text, has_arabic

# Process text
result = reverse_arabic_text("الحمد لله رب العالمين")
print(result)  # نيملاعلا بر هلل دمحلا

# Check if text contains Arabic characters
if has_arabic("Hello مرحبا"):
    print("Arabic text detected!")
```

### opencode Integration

This tool can be integrated as an [opencode](https://opencode.ai) skill. Copy `SKILL.md` to your opencode skills directory:

```bash
mkdir -p ~/.opencode/skills/arabic-rtl
cp SKILL.md ~/.opencode/skills/arabic-rtl/
```

### Requirements

* Python 3.10+
* Cython 3.0+
* GCC / Clang (for compiling native C extensions)

### Acknowledgments

Special thanks to the inspiring projects and creators whose performance techniques contributed to this project:
* **[1BRC Challenge (ifnesi/1brc)](https://github.com/ifnesi/1brc):** The 1 Billion Row Challenge that inspired high-performance optimization techniques.
* **[py-1brc (Ben Hoyt)](https://github.com/benhoyt/py-1brc):** Ben Hoyt's excellent repository on pushing Python performance to its extreme limits.

### Contributing

Contributions, issues, and feature requests are welcome! Feel free to open an Issue or submit a Pull Request.

### License

This project is licensed under the [MIT License](LICENSE).