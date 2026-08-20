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
        decide_process_count,
        get_optimal_process_count,
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
        if (0x10EC0 <= cp <= 0x10EFF) or (0x1EE00 <= cp <= 0x1EEFF):
            return True
        return False
    return bool(ARABIC_BITMAP[cp >> 3] & (1 << (cp & 7)))

def _is_arabic_punct(ch):
    return ord(ch) in (0x060C, 0x061B, 0x061F, 0x0640)

def _is_digit_char(c):
    cp = ord(c)
    return (48 <= cp <= 57) or (0x0660 <= cp <= 0x0669) or (0x06F0 <= cp <= 0x06F9)

def _is_diacritic(cp):
    return (
        (0x064B <= cp <= 0x065F) or
        cp == 0x0670 or
        (0x06D6 <= cp <= 0x06ED) or
        (0x08E3 <= cp <= 0x08FF) or
        (0x0610 <= cp <= 0x061A) or
        (0x0898 <= cp <= 0x089F) or
        (0x08CA <= cp <= 0x08E1) or
        cp in (0xFE70, 0xFE72, 0xFE74, 0xFE76, 0xFE78, 0xFE7A, 0xFE7C, 0xFE7E)
    )

import re

PREFIX_PATTERNS = [
    re.compile(r'^(#{1,6}\s+)'),
    re.compile(r'^(>\s*(?:\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*)?)'),
    re.compile(r'^(>+\s*)'),
    re.compile(r'^(\s*[-*+]\s+\[[ xX]\]\s+)'),
    re.compile(r'^(\s*[-*+]\s+)'),
    re.compile(r'^(\s*\d+[.)]\s+)'),
    re.compile(r'^(\s*[$#]\s+)'),
]

def py_has_arabic(text):
    return any(_is_arabic(c) for c in text)


def _py_scan_number(text, i, length):
    """Scan numbers, dates, times, percentages, keeping them LTR."""
    start = i
    if text[i] in ('+', '-') and i + 1 < length and _is_digit_char(text[i+1]):
        i += 1
    if i < length and _is_digit_char(text[i]):
        while i < length:
            if _is_digit_char(text[i]):
                i += 1
            elif text[i] in ('.', ',', ':', '/', '-', '_', '\u066B', '\u066C') and i + 1 < length and _is_digit_char(text[i+1]):
                i += 2
            else:
                break
        if i < length and text[i] in ('%', '\u066A', '\u2030'):
            i += 1
        return text[start:i], i - start
    return None, 0


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
        is_dig = _is_digit_char(ch)
        is_diac = _is_diacritic(cp)

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

def _has_arabic_in_bracket(line, i, length):
    ch = line[i]
    close_br = BRACKET_PAIRS.get(ch, None)
    if not close_br:
        return False
    end = line.find(close_br, i + 1)
    if end != -1:
        return py_has_arabic(line[i:end+1])
    return False


def _py_reverse_segment(segment):
    """Reverse an Arabic segment preserving words, numbers, and mirroring brackets."""
    length = len(segment)
    i = 0
    tokens = []

    while i < length:
        ch = segment[i]
        if ch in (' ', '\t'):
            start = i
            while i < length and segment[i] in (' ', '\t'):
                i += 1
            tokens.append(segment[start:i])
        elif ch in BRACKET_PAIRS:
            tokens.append(BRACKET_PAIRS[ch])
            i += 1
        else:
            start = i
            num_str, num_len = _py_scan_number(segment, i, length)
            if num_len > 0:
                tokens.append(num_str)
                i += num_len
            elif ord(ch) in (0x060C, 0x061B, 0x061F, 0x066A, 0x066B, 0x066C):
                tokens.append(ch)
                i += 1
            elif _is_arabic(ch):
                while i < length and segment[i] not in (' ', '\t', '\n', '\r') and segment[i] not in BRACKET_PAIRS:
                    c = ord(segment[i])
                    if _is_digit_char(segment[i]) or c in (0x060C, 0x061B, 0x061F, 0x066A, 0x066B, 0x066C):
                        break
                    i += 1
                word = segment[start:i]
                tokens.append(_py_reverse_arabic_word(word))
            else:
                while i < length and segment[i] not in (' ', '\t', '\n', '\r') and segment[i] not in BRACKET_PAIRS:
                    c = ord(segment[i])
                    if _is_arabic(segment[i]) or _is_digit_char(segment[i]) or c in (0x060C, 0x061B, 0x061F, 0x066A, 0x066B, 0x066C):
                        break
                    i += 1
                tokens.append(segment[start:i])

    tokens.reverse()
    return "".join(tokens)


def py_process_line(line, smart_mode=True):
    """Process a single line in pure Python."""
    if not py_has_arabic(line):
        return line

    prefix = ""
    if smart_mode:
        for pat in PREFIX_PATTERNS:
            m = pat.match(line)
            if m:
                prefix = m.group(1)
                line = line[len(prefix):]
                break

        if line.startswith("|") and line.endswith("|"):
            cells = line.split("|")
            proc_cells = [py_process_line(c, smart_mode=True) for c in cells[1:-1]]
            return prefix + "|" + "|".join(proc_cells) + "|"

    length = len(line)
    i = 0
    result = []

    while i < length:
        ansi_len = _scan_ansi_escape(line, i, length)
        if ansi_len > 0:
            result.append(line[i:i+ansi_len])
            i += ansi_len
            continue

        if smart_mode:
            # Skip code blocks (``` ... ```)
            if line.startswith("```", i):
                end = line.find("```", i + 3)
                if end == -1:
                    result.append(line[i:])
                    return prefix + "".join(result)
                else:
                    result.append(line[i:end + 3])
                    i = end + 3
                    continue

            # Skip inline code (` ... `)
            if line[i] == '`':
                end = line.find('`', i + 1)
                if end == -1:
                    result.append(line[i:])
                    return prefix + "".join(result)
                else:
                    result.append(line[i:end + 1])
                    i = end + 1
                    continue

            # Skip URLs and File paths
            if _is_path_start(line, i, length):
                end = i
                while end < length and line[end] not in (' ', '\t', '\n', '\r', '"', "'", ')', ']', '>'):
                    end += 1
                result.append(line[i:end])
                i = end
                continue

        # Check if Arabic segment starts here
        ch = line[i]
        is_br_arabic = (ch in BRACKET_PAIRS) and _has_arabic_in_bracket(line, i, length)
        if _is_arabic(ch) or is_br_arabic:
            seg_start = i
            last_arabic_i = i
            while i < length:
                ch = line[i]
                if _is_arabic(ch):
                    last_arabic_i = i
                    i += 1
                elif _scan_ansi_escape(line, i, length) > 0 or (smart_mode and (line.startswith("```", i) or line[i] == '`' or _is_path_start(line, i, length))):
                    break
                elif line[i] in ('\n', '\r'):
                    break
                else:
                    i += 1

            if not smart_mode:
                seg_end = last_arabic_i + 1
            else:
                seg_end = i
                trailing = line[last_arabic_i + 1 : seg_end]
                if "  " in trailing:
                    idx = trailing.find("  ")
                    seg_end = last_arabic_i + 1 + idx
                else:
                    while seg_end > last_arabic_i + 1:
                        prev_ch = line[seg_end - 1]
                        if prev_ch in (' ', '\t'):
                            seg_end -= 1
                        elif prev_ch in BRACKET_PAIRS or prev_ch in ('.', ',', '!', '?', ':', ';', '-'):
                            break
                        elif _is_digit_char(prev_ch):
                            break
                        else:
                            break

            i = seg_end
            segment = line[seg_start:seg_end]
            result.append(_py_reverse_segment(segment))
        else:
            result.append(line[i])
            i += 1

    return prefix + "".join(result)


def py_process_text(text, smart_mode=True):
    """Process Arabic prose. Auto-skip code blocks, etc. if smart_mode is True."""
    lines = text.split('\n')
    out = []
    in_code_block = False
    for line in lines:
        if smart_mode:
            stripped = line.strip()
            if in_code_block:
                out.append(line)
                if "```" in stripped:
                    in_code_block = False
            else:
                if stripped.startswith("```"):
                    out.append(line)
                    if stripped.count("```") % 2 != 0:
                        in_code_block = True
                else:
                    out.append(py_process_line(line, smart_mode=True))
        else:
            out.append(py_process_line(line, smart_mode=False))
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
    return py_process_text('\n'.join(chunk), smart_mode=smart_mode).split('\n')


def py_decide_process_count(text_or_lines, max_processes=None):
    """
    Determine the optimal number of worker processes based on text length.

    Balances multiprocessing startup/IPC overhead against parallel speedup:
    - Short text (< 100 lines and < 5,000 chars): 1 process (overhead exceeds gain)
    - Medium text (100 - 499 lines): 2 processes
    - Moderate text (500 - 1,999 lines): 4 processes
    - Large text (2,000 - 9,999 lines): 8 processes
    - Very large text (10,000+ lines): 16 processes

    Capped by CPU cores (or max_processes if provided).
    """
    if max_processes is not None and max_processes > 0:
        cpu_limit = max_processes
    else:
        try:
            cpu_limit = multiprocessing.cpu_count()
        except Exception:
            cpu_limit = 4

    cpu_limit = max(1, min(32, cpu_limit))

    if isinstance(text_or_lines, str):
        n_lines = text_or_lines.count('\n') + 1
        n_chars = len(text_or_lines)
    elif isinstance(text_or_lines, list):
        n_lines = len(text_or_lines)
        n_chars = sum(len(line) for line in text_or_lines)
    elif isinstance(text_or_lines, int):
        n_lines = text_or_lines
        n_chars = n_lines * 50
    else:
        return 1

    if n_lines < 100 and n_chars < 5000:
        return 1

    if n_lines < 500 and n_chars < 25000:
        target = 2
    elif n_lines < 2000 and n_chars < 100000:
        target = 4
    elif n_lines < 10000 and n_chars < 500000:
        target = 8
    else:
        target = 16

    return max(1, min(target, cpu_limit))


py_get_optimal_process_count = py_decide_process_count


def py_process_text_parallel(text, num_threads=0, smart_mode=True):
    """Process text using multiprocessing.Pool (bypasses GIL)."""
    if num_threads is None or num_threads <= 0:
        num_threads = py_decide_process_count(text)

    if num_threads < 1:
        num_threads = 1
    if num_threads > 32:
        num_threads = 32

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
def py_process_file_mmap(filepath, num_threads=0, output=None, smart_mode=True):
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

    if num_threads is None or num_threads <= 0:
        num_threads = py_decide_process_count(text)

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
    do_decide_process_count = decide_process_count
    # Also assign to module level
    decide_process_count = decide_process_count
    get_optimal_process_count = get_optimal_process_count
else:
    do_process_text = py_process_text
    do_process_text_parallel = py_process_text_parallel
    do_has_arabic = py_has_arabic
    do_process_file = py_process_file_mmap
    reverse_arabic_text = py_process_text
    do_decide_process_count = py_decide_process_count
    decide_process_count = py_decide_process_count
    get_optimal_process_count = py_decide_process_count


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
    parser.add_argument('--threads', '-t', type=int, default=None,
                        help='Number of processes (1-32, default: auto-decided based on text length)')
    parser.add_argument('--benchmark', '-b', action='store_true',
                        help='Run benchmark')
    parser.add_argument('--show-stats', '-s', action='store_true',
                        help='Show performance stats')
    parser.add_argument('--no-smart', action='store_true',
                        help='Disable smart mode (processes everything as text)')
    parser.add_argument('--stream', '-S', action='store_true',
                        help='Process stdin line-by-line in real-time (for logs/tail -f)')
    parser.add_argument('--daemon', '-d', action='store_true',
                        help='Use daemon mode (auto-starts if not running)')
    parser.add_argument('--version', '-v', action='version', version='arabic-rtl-processor 1.0.0')
    args = parser.parse_args()

    mode = "Cython/C" if FAST_MODE else "Pure Python (1BRC-optimized)"

    if args.benchmark:
        run_benchmark()
        return

    smart_mode = not args.no_smart

    # Stream mode: process line-by-line in real time
    if args.stream:
        for line in sys.stdin:
            if line.endswith('\n'):
                sys.stdout.write(do_process_text(line[:-1], smart_mode) + '\n')
            else:
                sys.stdout.write(do_process_text(line, smart_mode))
            sys.stdout.flush()
        return

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
        num_threads = max(1, min(32, args.threads)) if args.threads is not None else 0
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

    if args.threads is not None and args.threads > 0:
        num_threads = max(1, min(32, args.threads))
    else:
        num_threads = do_decide_process_count(text)

    start = time.perf_counter()

    if num_threads > 1 and text.count('\n') >= 100:
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
