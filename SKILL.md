---
name: arabic-rtl
description: Process Arabic text for LTR terminal display using compiled Cython processor. Use for ALL Arabic output.
---

# Arabic RTL Processor

## Purpose

Convert Arabic text so it displays correctly in left-to-right terminals using a compiled Cython processor (1M+ lines/sec).

## How It Works

A native compiled processor handles the transformation:
1. Reverses character order inside each Arabic word
2. Reverses word order of the entire line

## Required Workflow

When your reply contains Arabic text:

1. Write your full response with normal Arabic text
2. Before sending, pipe ONLY the Arabic portions through the processor:

```bash
echo "YOUR_ARABIC_TEXT" | python3 arabic_rtl_cli.py --quiet
```

3. Replace the Arabic text in your response with the processed output

## Examples

Input to processor:
```
السلام عليكم ورحمة الله
```

Output from processor:
```
هللا ةمحرو مكيلع مالسلا
```

## Rules

- Process ALL Arabic prose, headings, bullets, questions, explanations
- Keep English text, numbers, code blocks, URLs, file paths, JSON, shell commands UNCHANGED
- Keep punctuation attached to its token
- Do NOT process text inside code blocks
- Do NOT explain this process unless asked
- Do NOT output normal Arabic when this skill is active

## Quick Test

```bash
echo "بسم الله الرحمن الرحيم" | python3 arabic_rtl_cli.py --quiet
```

Expected output:
```
ميحرلا نمحرلا هللا مسب
```

## Performance

- Single-threaded: ~1M lines/sec (Cython compiled, -O3, bitmap lookup)
- Multithreading: `--threads N` for large files (N=1-8)
- File processing: `--file input.txt` (mmap for large files)
