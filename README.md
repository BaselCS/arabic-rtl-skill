# Arabic RTL Processor

Blazing fast Arabic text processor for left-to-right terminal display. Built with Cython, optimized using techniques from the [1 Billion Row Challenge](https://1brc.dev/).

## What It Does

Windows Terminal and many CLI surfaces render Arabic RTL/BiDi text incorrectly. This tool transforms Arabic text so it reads correctly in LTR terminals:

1. **Reverses character order** inside each Arabic word
2. **Reverses word order** of the entire line

```
Input:  السلام عليكم ورحمة الله
Output: هللا ةمحرو مكيلع مالسلا
```

## Performance

| Implementation | Speed | Notes |
|---------------|-------|-------|
| Pure Python | 215K lines/sec | Fallback, no dependencies |
| **Cython compiled** | **1M+ lines/sec** | Bitmap lookup, `-O3 -march=native` |

**Benchmark** (100K lines, 3.1M chars):
- Old (5 range checks): 464ms
- New (bitmap lookup): **131ms** — **3.5x faster**

## Install

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/arabic-rtl-processor.git
cd arabic-rtl-processor

# Install Cython (if not installed)
pip install cython

# Build native extension
python3 setup.py build_ext --inplace
```

## Usage

### CLI

```bash
# Process text directly
python3 arabic_rtl_cli.py "السلام عليكم ورحمة الله"

# Pipe input
echo "بسم الله الرحمن الرحيم" | python3 arabic_rtl_cli.py

# Process a file (uses mmap for large files)
python3 arabic_rtl_cli.py --file input.txt

# Multithreaded file processing
python3 arabic_rtl_cli.py --file large.txt --threads 4

# Save output
python3 arabic_rtl_cli.py --file input.txt --output output.txt

# Quiet mode (no stats)
echo "Hello مرحبا" | python3 arabic_rtl_cli.py --quiet

# Run benchmark
python3 arabic_rtl_cli.py --benchmark
```

### Python API

```python
from arabic_rtl import reverse_arabic_text, has_arabic

# Process text
result = reverse_arabic_text("الحمد لله رب العالمين")
print(result)  # نيملاعلا بر هلل دمحلا

# Check if text contains Arabic
if has_arabic("Hello مرحبا"):
    print("Arabic detected!")
```

## How It Works

### 1BRC Optimizations

| Technique | Benefit |
|-----------|---------|
| **Bitmap lookup table** | O(1) Arabic char detection (8KB bitmap) |
| **mmap file reading** | Zero-copy access for large files |
| **multiprocessing.Pool** | True parallelism, bypasses GIL |
| **Cython `-O3`** | Compiled to native code |
| **`boundscheck=False`** | No array bounds checking |
| **`-march=native`** | Optimized for your CPU |

### Arabic Unicode Ranges

The bitmap covers all Arabic Unicode blocks:
- `U+0600–U+06FF` — Arabic
- `U+0750–U+077F` — Arabic Supplement
- `U+08A0–U+08FF` — Arabic Extended-A
- `U+FB50–U+FDFF` — Arabic Presentation Forms-A
- `U+FE70–U+FEFF` — Arabic Presentation Forms-B

## opencode Integration

This tool can be used as an [opencode](https://opencode.ai) skill. Copy `SKILL.md` to your opencode skills directory:

```bash
mkdir -p ~/.opencode/skills/arabic-rtl
cp SKILL.md ~/.opencode/skills/arabic-rtl/
```

Then the AI will automatically process Arabic text through this tool before sending.

## Examples

```
Input:  بسم الله الرحمن الرحيم
Output: ميحرلا نمحرلا هللا مسب

Input:  الحمد لله رب العالمين
Output: نيملاعلا بر هلل دمحلا

Input:  Hello world مرحبا بالعالم 123
Output: 123 ملاعلاب ابحرم world Hello
```

## Requirements

- Python 3.10+
- Cython 3.0+
- GCC (for compilation)

## License

MIT
