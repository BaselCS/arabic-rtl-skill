<div align="center">

# Arabic RTL Processor — معالج النصوص العربية

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Cython](https://img.shields.io/badge/Cython-E5972C?style=for-the-badge&logo=cython&logoColor=white)](https://cython.org)
[![C](https://img.shields.io/badge/C-A8B9CC?style=for-the-badge&logo=c&logoColor=white)](https://en.wikipedia.org/wiki/C_(programming_language))
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![GitHub Release](https://img.shields.io/badge/Release-v1.0.0-blue?style=for-the-badge&logo=github)](https://github.com/baselCS/arabic-rtl-processor/releases)

**معالج نصوص عربي فائق السرعة لتصيير النصوص والتشكيل في الطرفيات (LTR Terminals)**
*A blazing-fast, 1BRC-style Arabic RTL & Cursive Shaping text processor designed for LTR monospace terminals.*

</div>

---

## Arabic / العربية

### معالج النصوص العربية — Arabic RTL Processor
أداة ومكتبة فائقة السرعة لمعالجة النصوص العربية وتشكيل الحروف المتصلة (Cursive Shaping) وتصحيح اتجاه القراءة من اليمين إلى اليسار (RTL) داخل بيئات الطرفية ذات العرض الأحادي (Monospace) التي لا تدعم اللغة العربية بشكل أصيل مثل (Ghostty, Alacritty, Kitty, Windows Terminal, WezTerm, Tmux).

### ملاحظة حول التطوير والمعمارية (1BRC Architecture)
تم بناء المحرك الأساسي بالكامل باستخدام **Cython / C** مع استلهام تقنيات معالجة البيانات الفائقة من تحدي المليار سطر (**1 Billion Row Challenge**):
* **تخصيص الذاكرة على المكدس (Stack Allocation):** معالجة السلاسل النصية وتشكيلها بدون حجز ديناميكي للذاكرة مع تعطيل قفل البايثون العام (`nogil`).
* **فحص الأحرف بجداول البتات (64-bit Bitmaps):** تصنيف الرموز والحركات والتشكيل بتعقيد زمني ثابت $O(1)$ عبر عمليات بتية مباشرة.
* **قراءة الملفات عبر خرائط الذاكرة (`mmap`):** وصول فوري للبيانات دون استهلاك إضافي للذاكرة مع معالجة متعددة العمليات (Multi-Processing) لتجاوز قفل GIL.
* **الحفاظ الذكي على الأكواد والتنسيقات:** تخطي تلقائي للروابط والمسارات والأرقام وكتل الأكواد البرمجية (Code Blocks) وعلامات Markdown.

### المميزات الأساسية
* **وضع الخادم السريع (Daemon Mode):** خادم خلفي عبر Unix domain sockets لاستجابة فورية بأقل من ملّي ثانية دون أي تأخير لبدء بايثون.
* **واجهة سطر أوامر ومكتبة برمجية:** دعم الأنابيب (`stdin/stdout`)، والملفات الضخمة، والاستدعاء المباشر من لغة بايثون.
* **محرك بديل تلقائي (Pure Python Fallback):** يعمل بسلاسة حتى في حال عدم توفر المترجم المدمج.

### التثبيت والاستخدام

#### 1. التثبيت السريع (موصى به)
```bash
git clone https://github.com/baselCS/arabic-rtl-processor.git
cd arabic-rtl-processor
bash install.sh
```

#### 2. التثبيت عبر `uv` أو `pip`
```bash
# باستخدام uv
uv venv
source .venv/bin/activate
uv pip install -e .
uv run setup.py build_ext --inplace

# أو باستخدام pip
pip install -e .
python setup.py build_ext --inplace
```

#### 3. استخدام سطر الأوامر (CLI)
```bash
# تمرير مباشر لنص
arabic-rtl "مرحبا بك في عالم البرمجة"

# التمرير عبر خط الأنابيب (Pipe)
echo "السلام عليكم ورحمة الله وبركاته" | arabic-rtl

# معالجة الملفات
arabic-rtl -f input.txt -o output.txt -t 4

# تشغيل وضع الخادم اللحظي
arabic-rtl-daemon start
echo "نص فائق السرعة" | arabic-rtl --daemon
```

### استخدام الأداة كمهارة للذكاء الاصطناعي (AI Skill)
يمكن تثبيت الأداة كمهارة (Skill) لمساعدي الذكاء الاصطناعي مثل [opencode](https://opencode.ai) و Antigravity لتصيير النصوص العربية بشكل سليم تلقائياً:

```bash
# تثبيت المهارة لـ opencode
mkdir -p ~/.config/opencode/skills/arabic-rtl
cp SKILL.md ~/.config/opencode/skills/arabic-rtl/

# تثبيت المهارة لـ Antigravity
mkdir -p ~/.gemini/config/skills/arabic-rtl
cp SKILL.md ~/.gemini/config/skills/arabic-rtl/
```

#### طريقة استخدام المساعد للمهارة:
يقوم المساعد بتمرير النص العربي المطلوب طباعته مباشرة عبر الأداة وطباعة الناتج:
```bash
arabic-rtl << 'EOF'
مرحبا بك! كيف يمكنني مساعدتك اليوم؟
EOF
```

### التقنيات المستخدمة
* **Core Engine:** [Cython](https://cython.org) / [C (C99)](https://en.wikipedia.org/wiki/C99)
* **Runtime:** [Python 3.10+](https://python.org)
* **Package Manager:** [uv](https://github.com/astral-sh/uv) / [Setuptools](https://setuptools.pypa.io)
* **Testing:** [pytest](https://pytest.org)

### شكر وتقدير (Acknowledgments)
شكر خاص للمشاريع الملهمة التي اعتمدنا على تقنياتها وأفكارها في تحسين الأداء:
* **[1BRC Challenge (ifnesi/1brc)](https://github.com/ifnesi/1brc):** تحدي الـ 1 Billion Row Challenge الملهم لتقنيات تحسين الأداء وتجاوز حدود السرعة.
* **[py-1brc (Ben Hoyt)](https://github.com/benhoyt/py-1brc):** مشروع Ben Hoyt المميز واستراتيجياته في تحسين أداء Python إلى أقصى سرعة ممكنة.

### المساهمة
المساهمات البرمجية والاقتراحات مرحب بها دائماً. يمكنك فتح [Issue](https://github.com/baselCS/arabic-rtl-processor/issues) أو إرسال [Pull Request](https://github.com/baselCS/arabic-rtl-processor/pulls) للمساهمة في تطوير المشروع.

### الترخيص
هذا المشروع مرخص تحت رخصة [MIT License](LICENSE).

---

## English

### Arabic RTL Processor App / Engine
A blazing-fast, lightweight Arabic text processor and cursive shaper designed specifically for Left-to-Right (LTR) monospace terminal emulators (Ghostty, Alacritty, Kitty, Windows Terminal, WezTerm, Tmux, etc.) that lack native bidirectional (BiDi) shaping support.

### Development & Architecture Notes (1BRC Techniques)
Engineered for extreme throughput and low latency, adopting optimizations from the **1 Billion Row Challenge**:
* **100% C Stack Allocation:** Token parsing, shaping, and RTL reversal execute inside fast C stack buffers with `nogil` (zero heap allocations in hot paths).
* **64-bit Bitmaps (`uint64_t`):** $O(1)$ single-cycle bitwise character and diacritic classification.
* **Direct C-API String Creation:** Efficient string synthesis avoiding intermediate Python overhead.
* **Memory-Mapped I/O (`mmap`):** Zero-copy file access coupled with process-pool parallelism for huge files.
* **Smart Token Parsing:** Automatic preservation of Markdown code blocks (` ``` `), inline code (`` ` ``), URLs, file paths, numbers, and bullet list prefixes.

### Core Features
- **Accurate Cursive Shaping:** Automatic conversion into Unicode Presentation Forms-B with complete Lam-Alef ligatures (`لا`, `لأ`, `لإ`, `لآ`) and optional Allah ligature (`ﷲ`).
- **Tashkeel & Diacritics Support:** Keeps multi-stacked Harakat and Quranic marks attached to base letters without breaking cursive joining connections.
- **Daemon Mode:** Background Unix domain socket / TCP daemon for zero-overhead, sub-millisecond repeated invocations (auto-terminates after 5 minutes of inactivity).
- **Comprehensive CLI & Python API:** Supports pipeline stdin/stdout, direct arguments, batch file processing, and direct Python imports.
- **Zero-Config Fallback:** Seamless fallback to pure Python engine if compiled C extension is unavailable.

### Installation & Usage

#### 1. Quick Install Script (Recommended)
```bash
git clone https://github.com/baselCS/arabic-rtl-processor.git
cd arabic-rtl-processor
bash install.sh
```

#### 2. Manual Setup (`uv` / `pip`)
```bash
# Using uv
uv venv
source .venv/bin/activate
uv pip install -e .
uv run setup.py build_ext --inplace

# Using standard pip
pip install -e .
python setup.py build_ext --inplace
```

#### 3. Command-Line Interface (CLI)
```bash
# Direct argument
arabic-rtl "مرحبا بك في عالم البرمجة"

# Pipe via stdin
echo "السلام عليكم ورحمة الله وبركاته" | arabic-rtl

# Process files with parallel workers
arabic-rtl -f input.txt -o output.txt -t 4

# Run performance benchmark suite
arabic-rtl --benchmark
```

#### 4. Daemon Mode (Sub-millisecond IPC)
```bash
# Start the background daemon
arabic-rtl-daemon start

# Route requests through active daemon
echo "نص عربي سريع جداً" | arabic-rtl --daemon

# Check status or stop
arabic-rtl-daemon status
arabic-rtl-daemon stop
```

#### 5. Python API
```python
from arabic_rtl import process_text, process_batch

# Single string
raw_text = "مرحبا بالعالم"
rendered = process_text(raw_text)
print(rendered)

# Batch processing
lines = ["السطر الأول", "السطر الثاني", "Console output: نجاح"]
results = process_batch(lines)
for line in results:
    print(line)
```

### AI Assistant Integration (Skills)
Integrate this tool as a skill with AI coding assistants such as [opencode](https://opencode.ai) or Antigravity to guarantee correct terminal Arabic rendering:

```bash
# Install skill for opencode
mkdir -p ~/.config/opencode/skills/arabic-rtl
cp SKILL.md ~/.config/opencode/skills/arabic-rtl/

# Install skill for Antigravity
mkdir -p ~/.gemini/config/skills/arabic-rtl
cp SKILL.md ~/.gemini/config/skills/arabic-rtl/
```

#### How AI Agents Use the Skill:
```bash
arabic-rtl << 'EOF'
مرحبا بك! كيف يمكنني مساعدتك اليوم؟
EOF
```

### CLI Options & Flags

| Flag | Long Option | Description |
|------|-------------|-------------|
| `-f` | `--file PATH` | Input file to process (uses `mmap` for large files) |
| `-o` | `--output PATH` | Output destination file (defaults to `stdout`) |
| `-t` | `--threads N` | Number of parallel worker processes (default: auto) |
| `-d` | `--daemon` | Route request through active `arabic-rtl-daemon` |
| `-s` | `--show-stats` | Print timing and throughput performance statistics |
| `-b` | `--benchmark` | Run built-in performance benchmark suite |
| `-kt` | `--keep-tashkeel` | Force preserve Arabic diacritics/harakat |
| `-nt` | `--no-tashkeel` | Strip all diacritics from output |
| `-al` | `--allah-ligature` | Convert `الله` sequence to Unicode ligature `ﷲ` (U+FDF2) |
| `-S` | `--stream` | Stream output line-by-line as it is read |
| `-r` | `--rtl` | Output terminal RTL override formatting |
| `-v` | `--version` | Display version number |

### Tech Stack
- **Core Engine:** [Cython](https://cython.org) / [C (C99)](https://en.wikipedia.org/wiki/C99)
- **Runtime:** [Python 3.10+](https://python.org)
- **Package Manager:** [uv](https://github.com/astral-sh/uv) / [Setuptools](https://setuptools.pypa.io)
- **Testing:** [pytest](https://pytest.org)

### Acknowledgments
Special thanks to the inspiring projects and creators whose performance techniques contributed to this project:
- **[1BRC Challenge (ifnesi/1brc)](https://github.com/ifnesi/1brc):** The 1 Billion Row Challenge that inspired high-performance optimization techniques.
- **[py-1brc (Ben Hoyt)](https://github.com/benhoyt/py-1brc):** Ben Hoyt's excellent repository on pushing Python performance to its extreme limits.

### Contributing
Contributions and suggestions are always welcome. Feel free to open an [Issue](https://github.com/baselCS/arabic-rtl-processor/issues) or submit a [Pull Request](https://github.com/baselCS/arabic-rtl-processor/pulls) to help improve the project.

### License
This project is licensed under the [MIT License](LICENSE).
