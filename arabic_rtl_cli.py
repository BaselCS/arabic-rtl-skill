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
        process_text,
        process_batch,
        has_arabic,
        process_text_parallel,
        process_file_parallel,
        reverse_arabic_text,
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
    for ch in range(0x0870, 0x0900):  # Extended-A & Extended-B
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


# Non-smart processing methods removed.


def py_has_arabic(text):
    return any(_is_arabic(c) for c in text)


def _py_reverse_arabic_word(word):
    """
    Reverse an Arabic word preserving Tashkeel (diacritics) on their base chars
    and keeping digit sequences (ASCII 0-9, Arabic ٠-٩, Persian ۰-۹) in LTR order.
    """
    if not word:
        return word

    sub_tokens = []
    curr_type = ""
    curr_token = []

    for ch in word:
        cp = ord(ch)
        is_dig = (48 <= cp <= 57) or (0x0660 <= cp <= 0x0669) or (0x06F0 <= cp <= 0x06F9)
        is_diac = (0x064B <= cp <= 0x065F) or cp == 0x0670 or (0x06D6 <= cp <= 0x06ED) or (0x08E3 <= cp <= 0x08FF) or (0x0610 <= cp <= 0x061A)

        if is_dig:
            if curr_type == "digit":
                curr_token.append(ch)
            else:
                if curr_token:
                    sub_tokens.append((curr_type, curr_token))
                curr_type = "digit"
                curr_token = [ch]
        elif is_diac and curr_type == "letter" and curr_token:
            curr_token[-1] = curr_token[-1] + ch
        else:
            if curr_type == "letter":
                curr_token.append(ch)
            else:
                if curr_token:
                    sub_tokens.append((curr_type, curr_token))
                curr_type = "letter"
                curr_token = [ch]

    if curr_token:
        sub_tokens.append((curr_type, curr_token))

    res_tokens = []
    for t_type, t_content in sub_tokens:
        if t_type == "digit":
            res_tokens.append("".join(t_content))
        else:
            t_content.reverse()
            res_tokens.append("".join(t_content))

    res_tokens.reverse()
    return "".join(res_tokens)


# ══════════════════════════════════════════════════════════════
# SMART MODE & ANSI SCANNER (Pure Python fallback)
# ══════════════════════════════════════════════════════════════

BRACKET_PAIRS = {
    '(': ')', ')': '(',
    '[': ']', ']': '[',
    '{': '}', '}': '{',
    '<': '>', '>': '<',
    '«': '»', '»': '«',
    '‹': '›', '›': '‹',
    '（': '）', '）': '（',
    '﴿': '﴾', '﴾': '﴿',
    '“': '”', '”': '“',
    '‘': '’', '’': '‘',
    '⦅': '⦆', '⦆': '⦅',
    '⟦': '⟧', '⟧': '⟦',
    '⟨': '⟩', '⟩': '⟨',
    '【': '】', '】': '【',
    '〔': '〕', '〕': '〔',
    '〖': '〗', '〗': '〖',
    '⁅': '⁆', '⁆': '⁅',
}

def _scan_ansi_escape(line, i, length):
    """Scan ANSI escape sequence starting at index i. Returns length of sequence or 0."""
    if i >= length or line[i] not in ('\x1b', '\033'):
        return 0
    if i + 1 >= length:
        return 1
    next_ch = line[i + 1]
    if next_ch == '[':
        end = i + 2
        while end < length and 0x20 <= ord(line[end]) <= 0x3F:
            end += 1
        if end < length and 0x40 <= ord(line[end]) <= 0x7E:
            end += 1
        return end - i
    elif next_ch in (']', 'P', '^', '_'):
        end = i + 2
        while end < length:
            if line[end] == '\x07':
                end += 1
                break
            if line[end:end + 2] in ('\x1b\\', '\033\\'):
                end += 2
                break
            end += 1
        return end - i
    else:
        end = i + 1
        while end < length and 0x20 <= ord(line[end]) <= 0x2F:
            end += 1
        if end < length and 0x30 <= ord(line[end]) <= 0x7E:
            end += 1
        return end - i

def _is_path_start(line, i, length):
    """Check if position i starts a file path or URL."""
    # URLs
    if (line[i:i+7] == "http://" or line[i:i+8] == "https://" or
        line[i:i+6] == "ftp://" or line[i:i+7] == "file://" or
        line[i:i+7] == "mailto:" or line[i:i+4] == "git@" or
        line[i:i+6] == "ssh://" or line[i:i+5] == "ws://" or
        line[i:i+6] == "wss://" or line[i:i+7] == "sftp://" or
        line[i:i+6] == "git://" or line[i:i+6] == "svn://"):
        return True
    # Unix paths (/ or ~/) or Env vars ($ or %)
    if (i == 0 or line[i-1] in (' ', '\t', '"', "'", '(', '[', '<', '=', ':', 'm', 'M', ';', 'g')):
        if line[i] in ('/', '$', '%') or line[i:i+2] in ('~/', './') or line[i:i+3] == '../':
            # Avoid division operator like "1 / 2"
            if line[i] == '/' and (i + 1 >= length or line[i+1] in (' ', '\t', '\n', '\r')):
                return False
            return True
        # Windows drive paths (C:\ or C:/ or .\ or ..\)
        if i + 2 < length and line[i+1] == ':' and line[i+2] in ('\\', '/'):
            if ('A' <= line[i] <= 'Z') or ('a' <= line[i] <= 'z'):
                return True
        if line[i:i+2] == '.\\' or line[i:i+3] == '..\\':
            return True
    return False

def py_smart_process_line(line):
    """Process a line, skipping code blocks, URLs, paths, commands, and ANSI sequences."""
    length = len(line)
    i = 0
    result = ""

    while i < length:
        # Skip ANSI escape sequences
        ansi_len = _scan_ansi_escape(line, i, length)
        if ansi_len > 0:
            result += line[i:i+ansi_len]
            i += ansi_len
            continue

        # Skip code blocks (``` ... ```)
        if line[i:i+3] == "```":
            end = line.find("```", i + 3)
            if end == -1:
                result += line[i:]
                return result
            else:
                result += line[i:end + 3]
                i = end + 3
                continue

        # Skip inline code (` ... `)
        if line[i] == '`':
            end = line.find('`', i + 1)
            if end == -1:
                result += line[i:]
                return result
            else:
                result += line[i:end + 1]
                i = end + 1
                continue

        # Skip URLs and File Paths
        if _is_path_start(line, i, length):
            end = i
            while end < length and line[end] not in (' ', '\t', '\n', '\r', '"', "'", ')', ']', '>'):
                end += 1
            result += line[i:end]
            i = end
            continue

        # Process this character normally
        ch = line[i]
        if _is_arabic(ch):
            # Find boundary of Arabic segment
            seg_start = i
            last_arabic_i = i
            while i < length:
                ch = line[i]
                if _is_arabic(ch):
                    last_arabic_i = i
                    i += 1
                elif _scan_ansi_escape(line, i, length) > 0 or _is_path_start(line, i, length) or line[i:i+3] == "```" or line[i] == '`':
                    break
                elif ch in ('\n', '\r'):
                    break
                else:
                    i += 1

            seg_end = i
            while seg_end > last_arabic_i + 1:
                prev_ch = line[seg_end - 1]
                if prev_ch in (' ', '\t'):
                    seg_end -= 1
                elif prev_ch in BRACKET_PAIRS or prev_ch in ('.', ',', '!', '?', ':', ';', '-'):
                    break
                elif (48 <= ord(prev_ch) <= 57) or (0x0660 <= ord(prev_ch) <= 0x0669) or (0x06F0 <= ord(prev_ch) <= 0x06F9):
                    break
                else:
                    seg_end -= 1

            i = seg_end
            segment = line[seg_start:seg_end]
            result += _py_reverse_segment(segment)
        else:
            result += line[i]
            i += 1

    return result

def _py_reverse_segment(segment):
    """Reverse an Arabic segment preserving words, numbers, and mirroring brackets."""
    tokens = []
    seg_i = 0
    seg_len = len(segment)

    while seg_i < seg_len:
        ch = segment[seg_i]
        if ch == ' ':
            start = seg_i
            while seg_i < seg_len and segment[seg_i] == ' ':
                seg_i += 1
            tokens.append(segment[start:seg_i])
        elif ch in BRACKET_PAIRS:
            tokens.append(BRACKET_PAIRS[ch])
            seg_i += 1
        else:
            start = seg_i
            cp = ord(ch)
            is_digit = (48 <= cp <= 57) or (0x0660 <= cp <= 0x0669) or (0x06F0 <= cp <= 0x06F9)
            if is_digit:
                while seg_i < seg_len:
                    c = ord(segment[seg_i])
                    if (48 <= c <= 57) or (0x0660 <= c <= 0x0669) or (0x06F0 <= c <= 0x06F9):
                        seg_i += 1
                    else:
                        break
                tokens.append(segment[start:seg_i])
            elif cp in (0x060C, 0x061B, 0x061F, 0x066A, 0x066B, 0x066C):
                tokens.append(ch)
                seg_i += 1
            elif _is_arabic(ch):
                while seg_i < seg_len and segment[seg_i] not in (' ', '\n', '\r') and segment[seg_i] not in BRACKET_PAIRS:
                    c = ord(segment[seg_i])
                    if (48 <= c <= 57) or (0x0660 <= c <= 0x0669) or (0x06F0 <= c <= 0x06F9) or c in (0x060C, 0x061B, 0x061F, 0x066A, 0x066B, 0x066C):
                        break
                    seg_i += 1
                word = segment[start:seg_i]
                tokens.append(_py_reverse_arabic_word(word))
            else:
                while seg_i < seg_len and segment[seg_i] not in (' ', '\n', '\r') and segment[seg_i] not in BRACKET_PAIRS and not _is_arabic(segment[seg_i]):
                    seg_i += 1
                tokens.append(segment[start:seg_i])

    tokens.reverse()
    return "".join(tokens)


def py_process_line_normal(line):
    """Process a line without smart skipping."""
    length = len(line)
    i = 0
    result = ""

    while i < length:
        # Skip ANSI escape sequences
        ansi_len = _scan_ansi_escape(line, i, length)
        if ansi_len > 0:
            result += line[i:i+ansi_len]
            i += ansi_len
            continue

        ch = line[i]
        if _is_arabic(ch):
            seg_start = i
            last_arabic_i = i
            while i < length:
                ch = line[i]
                if _is_arabic(ch):
                    last_arabic_i = i
                elif _scan_ansi_escape(line, i, length) > 0 or ch in ('\n', '\r'):
                    break
                i += 1
            seg_end = last_arabic_i + 1
            i = seg_end
            segment = line[seg_start:seg_end]
            result += _py_reverse_segment(segment)
        else:
            result += line[i]
            i += 1
    return result


def py_process_text(text, smart_mode=True):
    """Process Arabic prose. Auto-skip code blocks, etc. if smart_mode is True."""
    lines = text.split('\n')
    if not smart_mode:
        return '\n'.join(py_process_line_normal(line) for line in lines)

    out = []
    in_code_block = False
    for line in lines:
        stripped = line.strip()
        if in_code_block:
            out.append(line)
            if "```" in stripped:
                in_code_block = False
        else:
            if stripped.startswith("```"):
                out.append(py_smart_process_line(line))
                if stripped.count("```") % 2 != 0:
                    in_code_block = True
            else:
                out.append(py_smart_process_line(line))
    return '\n'.join(out)

py_reverse_arabic_text = py_process_text


def _split_lines(lines, num_chunks, smart_mode=True):
    n = len(lines)
    if n > 0 and num_chunks > n:
        num_chunks = n
    if num_chunks <= 1 or n == 0:
        return [lines]
    target_chunk_size = n // num_chunks
    chunks = []
    start = 0
    in_code_block = False

    for i in range(n):
        if smart_mode:
            stripped = lines[i].strip()
            if in_code_block:
                if "```" in stripped:
                    in_code_block = False
            else:
                if stripped.startswith("```") and stripped.count("```") % 2 != 0:
                    in_code_block = True

        if not in_code_block and (i - start + 1) >= target_chunk_size and len(chunks) < num_chunks - 1:
            chunks.append(lines[start:i + 1])
            start = i + 1

    if start < n:
        chunks.append(lines[start:])
    return chunks


def _process_chunk(args):
    """Worker function for multiprocessing."""
    chunk, smart_mode = args
    if smart_mode:
        return py_process_text('\n'.join(chunk), smart_mode=True).split('\n')
    else:
        return [py_process_line_normal(line) for line in chunk]


def py_process_text_parallel(text, num_threads=4, smart_mode=True):
    """Process text using multiprocessing.Pool (bypasses GIL)."""
    lines = text.split('\n')
    n = len(lines)

    if n < 100 or num_threads <= 1:
        return py_process_text(text, smart_mode)

    chunks = _split_lines(lines, num_threads, smart_mode)
    chunk_args = [(chunk, smart_mode) for chunk in chunks]

    with multiprocessing.Pool(num_threads) as pool:
        results = pool.map(_process_chunk, chunk_args)

    out = []
    for chunk_result in results:
        out.extend(chunk_result)
    return '\n'.join(out)


# 1BRC Technique: mmap-based file reading
def py_process_file_mmap(filepath, num_threads=4, output=None, smart_mode=True):
    """Process file using mmap (zero-copy file access)."""
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found.", file=sys.stderr)
        return ""

    try:
        file_size = os.path.getsize(filepath)

        if file_size > 1_000_000:
            with open(filepath, 'rb') as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    raw = mm[:]
        else:
            with open(filepath, 'rb') as f:
                raw = f.read()
    except OSError as e:
        print(f"Error: Could not read file '{filepath}': {e}", file=sys.stderr)
        return ""

    text = raw.decode('utf-8', errors='replace')

    if num_threads > 1:
        result = py_process_text_parallel(text, num_threads, smart_mode)
    else:
        result = py_process_text(text, smart_mode)

    if output:
        try:
            with open(output, 'w', encoding='utf-8') as f:
                f.write(result)
        except OSError as e:
            print(f"Error: Could not write output file '{output}': {e}", file=sys.stderr)
    else:
        print(result)

    return result


# ══════════════════════════════════════════════════════════════
# Dispatcher (picks fastest available implementation)
# ══════════════════════════════════════════════════════════════

if FAST_MODE:
    do_process_text = process_text
    do_process_text_parallel = process_text_parallel
    do_has_arabic = has_arabic
    do_process_file = process_file_parallel
else:
    do_process_text = py_process_text
    do_process_text_parallel = py_process_text_parallel
    do_has_arabic = py_has_arabic
    do_process_file = py_process_file_mmap
    reverse_arabic_text = py_process_text


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

def _configure_std_streams():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass

def main():
    _configure_std_streams()
    parser = argparse.ArgumentParser(
        description='Fast Arabic RTL processor (1BRC-optimized)'
    )
    parser.add_argument('text', nargs='?', help='Arabic text to process')
    parser.add_argument('--file', '-f', help='Process a file (uses mmap for large files)')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    default_threads = multiprocessing.cpu_count()
    parser.add_argument('--threads', '-t', type=int, default=default_threads,
                        help=f'Number of processes (1-32, default: {default_threads})')
    parser.add_argument('--benchmark', '-b', action='store_true',
                        help='Run benchmark')
    parser.add_argument('--show-stats', '-s', action='store_true',
                        help='Show performance stats')
    parser.add_argument('--no-smart', action='store_true',
                        help='Disable smart mode (processes everything as text)')
    parser.add_argument('--daemon', '-d', action='store_true',
                        help='Use daemon mode (auto-starts if not running)')
    parser.add_argument('--version', '-v', action='version', version='arabic-rtl-processor 1.0.0')
    args = parser.parse_args()


    num_threads = max(1, min(32, args.threads))
    mode = "Cython/C" if FAST_MODE else "Pure Python (1BRC-optimized)"

    if args.benchmark:
        run_benchmark()
        return

    smart_mode = not args.no_smart

    # Daemon mode: send to daemon and exit
    if args.daemon:
        from arabic_rtl_daemon import send_to_daemon
        if args.text:
            text = args.text
        elif not sys.stdin.isatty():
            text = sys.stdin.read()
        else:
            parser.print_help()
            return
        result = send_to_daemon(text, smart_mode)
        print(result, end='')
        return

    # File processing (1BRC-style mmap + parallel)
    if args.file:
        result = do_process_file(args.file, num_threads, args.output, smart_mode)
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
        result = do_process_text_parallel(text, num_threads, smart_mode)
    else:
        result = do_process_text(text, smart_mode)

    elapsed = time.perf_counter() - start

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result)
    elif text:
        print(result)

    if args.show_stats:
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
        result_text = do_process_text_parallel(full_text, nt) if nt > 1 else \
                      do_process_text(full_text)
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
        got = do_process_text(inp)
        status = "PASS" if got == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"    {status}: \"{inp}\" -> \"{got}\"")

    print("=" * 65)
    print(f"  Result: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    print("=" * 65)


if __name__ == '__main__':
    main()
