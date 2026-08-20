#!/usr/bin/env python3
"""
arabic_rtl_cli — 1BRC-style Arabic RTL processor for LTR terminals.

Optimizations inspired by the 1 Billion Row Challenge:
1. Bitmap lookup table for O(1) Arabic char detection
2. mmap-based file reading for zero-copy access
3. multiprocessing.Pool for true parallelism (bypass GIL)
4. Pre-computed lookup tables
5. Chunk-based splitting for parallel processing
6. Binary-mode file reading

Usage:
    echo "السلام عليكم" | python3 arabic_rtl_cli.py
    python3 arabic_rtl_cli.py "السلام عليكم ورحمة الله"
    python3 arabic_rtl_cli.py --file input.txt --threads 4
    python3 arabic_rtl_cli.py --benchmark
    cat large_file.txt | python3 arabic_rtl_cli.py -t 8
"""

import sys
import os
import time
import argparse
import mmap
import multiprocessing

# Try compiled Cython module first
try:
    from arabic_rtl import (
        reverse_arabic_text,
        reverse_arabic_batch,
        has_arabic,
        reverse_arabic_text_parallel,
        process_file_parallel,
        process_file_mmap,
    )
    FAST_MODE = True
except ImportError:
    FAST_MODE = False


# ══════════════════════════════════════════════════════════════
# Pure Python fallback (still uses 1BRC techniques)
# ══════════════════════════════════════════════════════════════

# 1BRC Technique: Pre-computed bitmap for O(1) Arabic detection
ARABIC_BITMAP = bytearray(8192)  # 65536 bits

def _init_bitmap():
    """Initialize Arabic character bitmap (runs once at import)."""
    for ch in range(0x0600, 0x0700):
        ARABIC_BITMAP[ch >> 3] |= 1 << (ch & 7)
    for ch in range(0x0750, 0x0780):
        ARABIC_BITMAP[ch >> 3] |= 1 << (ch & 7)
    for ch in range(0x08A0, 0x0900):
        ARABIC_BITMAP[ch >> 3] |= 1 << (ch & 7)
    for ch in range(0xFB50, 0xFE00):
        ARABIC_BITMAP[ch >> 3] |= 1 << (ch & 7)
    for ch in range(0xFE70, 0xFF00):
        ARABIC_BITMAP[ch >> 3] |= 1 << (ch & 7)
    for ch in [0x060C, 0x061B, 0x061F, 0x0640]:
        ARABIC_BITMAP[ch >> 3] |= 1 << (ch & 7)

_init_bitmap()

def _is_arabic(ch):
    cp = ord(ch)
    if cp > 0xFFFF:
        return False
    return bool(ARABIC_BITMAP[cp >> 3] & (1 << (cp & 7)))

def _is_arabic_punct(ch):
    return ord(ch) in (0x060C, 0x061B, 0x061F, 0x0640)


def py_process_line(line):
    """Process a single line with bitmap-based detection."""
    if not line:
        return line

    words = []
    for word in line.split():
        has_arab = False
        for ch in word:
            if _is_arabic(ch):
                has_arab = True
                break

        if has_arab:
            end = len(word)
            while end > 1 and _is_arabic_punct(word[end - 1]):
                end -= 1
            core = word[:end]
            trail = word[end:]
            words.append(core[::-1] + trail)
        else:
            words.append(word)

    words.reverse()
    return ' '.join(words)


def py_reverse_arabic_text(text):
    return '\n'.join(py_process_line(line) for line in text.split('\n'))


def py_has_arabic(text):
    return any(_is_arabic(c) for c in text)


# 1BRC Technique: Chunk-based splitting for multiprocessing
def _split_lines(lines, num_chunks):
    n = len(lines)
    chunk_size = n // num_chunks
    chunks = []
    start = 0
    for i in range(num_chunks - 1):
        end = start + chunk_size
        chunks.append(lines[start:end])
        start = end
    chunks.append(lines[start:])
    return chunks


def _process_chunk(chunk):
    """Worker function for multiprocessing."""
    return [py_process_line(line) for line in chunk]


def py_reverse_parallel(text, num_threads=4):
    """Process text using multiprocessing.Pool (bypasses GIL)."""
    lines = text.split('\n')
    n = len(lines)

    if n < 100 or num_threads <= 1:
        return py_reverse_arabic_text(text)

    chunks = _split_lines(lines, num_threads)
    with multiprocessing.Pool(num_threads) as pool:
        results = pool.map(_process_chunk, chunks)

    out = []
    for chunk_result in results:
        out.extend(chunk_result)
    return '\n'.join(out)


# 1BRC Technique: mmap-based file reading
def py_process_file_mmap(filepath, num_threads=4):
    """Process file using mmap (zero-copy file access)."""
    file_size = os.path.getsize(filepath)

    if file_size > 1_000_000:
        with open(filepath, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                raw = mm[:]
    else:
        with open(filepath, 'rb') as f:
            raw = f.read()

    text = raw.decode('utf-8', errors='replace')

    if num_threads > 1:
        return py_reverse_parallel(text, num_threads)
    else:
        return py_reverse_arabic_text(text)


# ══════════════════════════════════════════════════════════════
# Dispatcher (picks fastest available implementation)
# ══════════════════════════════════════════════════════════════

if FAST_MODE:
    do_reverse = reverse_arabic_text
    do_reverse_parallel = reverse_arabic_text_parallel
    do_has_arabic = has_arabic
    do_process_file = process_file_parallel
else:
    do_reverse = py_reverse_arabic_text
    do_reverse_parallel = py_reverse_parallel
    do_has_arabic = py_has_arabic
    do_process_file = py_process_file_mmap


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='Fast Arabic RTL processor (1BRC-optimized)'
    )
    parser.add_argument('text', nargs='?', help='Arabic text to process')
    parser.add_argument('--file', '-f', help='Process a file (uses mmap for large files)')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    parser.add_argument('--threads', '-t', type=int, default=1,
                        help='Number of processes (1-8, default: 1)')
    parser.add_argument('--benchmark', '-b', action='store_true',
                        help='Run benchmark')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Suppress stats')
    args = parser.parse_args()

    num_threads = max(1, min(8, args.threads))
    mode = "Cython/C" if FAST_MODE else "Pure Python (1BRC-optimized)"

    if args.benchmark:
        run_benchmark()
        return

    # File processing (1BRC-style mmap + parallel)
    if args.file:
        result = do_process_file(args.file, num_threads, args.output)
        return

    # Text input
    if args.text:
        text = args.text
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        parser.print_help()
        return

    start = time.perf_counter()

    if num_threads > 1 and text.count('\n') > 100:
        result = do_reverse_parallel(text, num_threads)
    else:
        result = do_reverse(text)

    elapsed = time.perf_counter() - start

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result)
    else:
        print(result)

    if not args.quiet:
        lines_count = text.count('\n') + 1
        throughput = lines_count / elapsed if elapsed > 0 else 0
        print(f"\n--- {mode} | {num_threads} proc(s) | "
              f"{len(text)} chars | {lines_count} lines | "
              f"{elapsed*1000:.2f}ms | {throughput:,.0f} lines/sec ---",
              file=sys.stderr)


def run_benchmark():
    """Comprehensive benchmark with 1BRC-style measurements."""
    test_lines = [
        "السلام عليكم ورحمة الله",
        "بسم الله الرحمن الرحيم",
        "الحمد لله رب العالمين",
        "لا إله إلا الله وحده لا شريك له",
        "سبحان الله وبحمده سبحان الله العظيم",
        "Hello world مرحبا بالعالم 123",
        "This is a mixed line مع بعض الكلمات العربية and English",
        "أرسل نص عربي到中文 and numbers 456",
    ] * 1000  # 8000 lines

    mode = "Cython/C" if FAST_MODE else "Pure Python"
    total_chars = sum(len(line) for line in test_lines)

    print("=" * 65)
    print(f"  Arabic RTL Benchmark (1BRC-style) — {mode}")
    print("=" * 65)
    print(f"  Dataset: {len(test_lines):,} lines | {total_chars:,} chars")
    print("-" * 65)

    # Test different thread counts
    full_text = '\n'.join(test_lines)
    for nt in [1, 2, 4, 8]:
        start = time.perf_counter()
        result_text = do_reverse_parallel(full_text, nt) if nt > 1 else \
                      do_reverse(full_text)
        elapsed = time.perf_counter() - start
        result_lines = result_text.split('\n')
        throughput = len(test_lines) / elapsed if elapsed > 0 else 0
        print(f"  {nt:>2} process(es): {elapsed*1000:>8.1f}ms | "
              f"{throughput:>10,.0f} lines/sec | {len(result_lines):,} results")

    print("-" * 65)

    # Correctness checks
    tests = [
        ("الحمد لله", "هلل دمحلا"),
        ("السلام عليكم ورحمة الله", "هللا ةمحرو مكيلع مالسلا"),
        ("بسم الله الرحمن الرحيم", "ميحرلا نمحرلا هللا مسب"),
    ]

    print("  Correctness:")
    all_pass = True
    for inp, expected in tests:
        got = do_reverse(inp)
        status = "PASS" if got == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"    {status}: \"{inp}\" -> \"{got}\"")

    print("=" * 65)
    print(f"  Result: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    print("=" * 65)


if __name__ == '__main__':
    main()
