# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
# cython: initializedcheck=False, nonecheck=False

"""
Arabic RTL Fast Processor — 1BRC-inspired optimizations.

Techniques from the 1 Billion Row Challenge applied to Arabic text:
1. Bitmap lookup table for O(1) Arabic char detection (instead of range checks)
2. mmap-based file processing for zero-copy file access
3. multiprocessing.Pool for true parallelism (bypass GIL)
4. Pre-computed lookup tables (like the floats{} dict in 1BRC)
5. Binary-level processing where possible
6. Chunk-based splitting for parallel file processing
"""

from libc.stdlib cimport malloc, free
from libc.string cimport memcpy
import mmap
import os
import multiprocessing
import sys
import re

# ══════════════════════════════════════════════════════════════
# 1BRC TECHNIQUE 1: Bitmap lookup table for O(1) Arabic detection
# Instead of 5 range checks per character, use a 256-byte bitmap
# for the BMP (Basic Multilingual Plane) Arabic block.
# ══════════════════════════════════════════════════════════════

# Arabic Unicode ranges to bitmap positions:
# 0x0600-0x06FF (Arabic) → bitmap[0x06] through bitmap[0x06]
# 0x0750-0x077F (Arabic Supplement) → bitmap[0x07]
# 0x08A0-0x08FF (Arabic Extended-A) → bitmap[0x08]
# 0xFB50-0xFDFF (Arabic Presentation A) → bitmap[0xFB]-0xFD
# 0xFE70-0xFEFF (Arabic Presentation B) → bitmap[0xFE]-0xFF

# Build a 65536-bit bitmap (8192 bytes) for all BMP Arabic chars
# Each bit represents one Unicode codepoint in the BMP

cdef unsigned char ARABIC_BITMAP[8192]  # 65536 bits = 8192 bytes

cdef void init_arabic_bitmap() noexcept nogil:
    """Initialize the Arabic character bitmap lookup table."""
    cdef unsigned int ch
    cdef unsigned int byte_idx, bit_idx
    cdef int i

    # Clear bitmap
    for i in range(8192):
        ARABIC_BITMAP[i] = 0

    # Set bits for Arabic ranges
    for ch in range(0x0600, 0x0700):  # Arabic block
        byte_idx = ch >> 3
        bit_idx = ch & 7
        ARABIC_BITMAP[byte_idx] |= (1 << bit_idx)

    for ch in range(0x0750, 0x0780):  # Arabic Supplement
        byte_idx = ch >> 3
        bit_idx = ch & 7
        ARABIC_BITMAP[byte_idx] |= (1 << bit_idx)

    for ch in range(0x0870, 0x0900):  # Arabic Extended-A & Extended-B
        byte_idx = ch >> 3
        bit_idx = ch & 7
        ARABIC_BITMAP[byte_idx] |= (1 << bit_idx)

    for ch in range(0xFB50, 0xFE00):  # Arabic Presentation Forms-A
        byte_idx = ch >> 3
        bit_idx = ch & 7
        ARABIC_BITMAP[byte_idx] |= (1 << bit_idx)

    for ch in range(0xFE70, 0xFF00):  # Arabic Presentation Forms-B
        byte_idx = ch >> 3
        bit_idx = ch & 7
        ARABIC_BITMAP[byte_idx] |= (1 << bit_idx)

    # Arabic punctuation (individual assignments to avoid Python list in nogil)
    ch = 0x060C; ARABIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    ch = 0x061B; ARABIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    ch = 0x061F; ARABIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    ch = 0x0640; ARABIC_BITMAP[ch >> 3] |= (1 << (ch & 7))


cdef inline bint is_arabic_fast(unsigned int ch) noexcept nogil:
    """O(1) Arabic character check using bitmap lookup."""
    if ch > 0xFFFF:
        if (0x10EC0 <= ch <= 0x10EFF) or (0x1EE00 <= ch <= 0x1EEFF):
            return True
        return False
    return (ARABIC_BITMAP[ch >> 3] >> (ch & 7)) & 1


# Initialize on module load
init_arabic_bitmap()

cdef list PREFIX_PATTERNS = [
    re.compile(r'^(#{1,6}\s+)'),
    re.compile(r'^(>\s*(?:\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*)?)'),
    re.compile(r'^(>+\s*)'),
    re.compile(r'^(\s*[-*+]\s+\[[ xX]\]\s+)'),
    re.compile(r'^(\s*[-*+]\s+)'),
    re.compile(r'^(\s*\d+[.)]\s+)'),
    re.compile(r'^(\s*[$#]\s+)'),
]

cdef inline bint _is_digit_cp(unsigned int cp) noexcept nogil:
    return (48 <= cp <= 57) or (0x0660 <= cp <= 0x0669) or (0x06F0 <= cp <= 0x06F9)

cdef inline bint _is_diacritic_cp(unsigned int cp) noexcept nogil:
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


# ══════════════════════════════════════════════════════════════
# 1BRC TECHNIQUE 2: Pre-computed lookup table (like floats{} dict)
# Pre-compute reversed Arabic word mappings for common words
# ══════════════════════════════════════════════════════════════

# For very common short Arabic words, pre-compute the reversal
# This is like the floats{} lookup table in 1BRC

# ══════════════════════════════════════════════════════════════
# Core processing functions
# ══════════════════════════════════════════════════════════════


def process_batch(list texts, int num_threads=4, bint smart_mode=True):
    """Process multiple strings."""
    cdef Py_ssize_t n = len(texts)
    cdef list results = [None] * n
    cdef Py_ssize_t i
    for i in range(n):
        results[i] = process_text(texts[i], smart_mode)
    return results


def has_arabic(str text):
    """Fast check using bitmap lookup."""
    cdef Py_ssize_t length = len(text)
    if length == 0:
        return False
    cdef Py_ssize_t j
    cdef unsigned int ch
    for j in range(length):
        ch = <unsigned int>ord(text[j])
        if is_arabic_fast(ch):
            return True
    return False


# ══════════════════════════════════════════════════════════════
# 1BRC TECHNIQUE 3: mmap-based file processing
# Memory-mapped files for zero-copy access
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
# 1BRC TECHNIQUE 4: multiprocessing.Pool (bypass GIL)
# Split text into chunks and process in parallel
# ══════════════════════════════════════════════════════════════

cdef list split_lines(list lines, int num_chunks, bint smart_mode=True):
    """Split lines into roughly equal chunks, respecting code block boundaries."""
    cdef Py_ssize_t n = len(lines)
    if n > 0 and num_chunks > n:
        num_chunks = n
    if num_chunks <= 1 or n == 0:
        return [lines]
    cdef Py_ssize_t target_chunk_size = n // num_chunks
    cdef list chunks = []
    cdef Py_ssize_t start = 0
    cdef Py_ssize_t i = 0
    cdef bint in_code_block = False
    cdef str stripped

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


def decide_process_count(text_or_lines, int max_processes=0):
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
    cdef Py_ssize_t n_lines = 0
    cdef Py_ssize_t n_chars = 0
    cdef int cpu_limit

    if max_processes > 0:
        cpu_limit = max_processes
    else:
        try:
            cpu_limit = multiprocessing.cpu_count()
        except Exception:
            cpu_limit = 4

    if cpu_limit < 1:
        cpu_limit = 1
    elif cpu_limit > 32:
        cpu_limit = 32

    if isinstance(text_or_lines, str):
        n_lines = (<str>text_or_lines).count('\n') + 1
        n_chars = len(<str>text_or_lines)
    elif isinstance(text_or_lines, list):
        n_lines = len(<list>text_or_lines)
        n_chars = sum(len(line) for line in <list>text_or_lines)
    elif isinstance(text_or_lines, int):
        n_lines = <int>text_or_lines
        n_chars = n_lines * 50
    else:
        return 1

    if n_lines < 100 and n_chars < 5000:
        return 1

    cdef int target
    if n_lines < 500 and n_chars < 25000:
        target = 2
    elif n_lines < 2000 and n_chars < 100000:
        target = 4
    elif n_lines < 10000 and n_chars < 500000:
        target = 8
    else:
        target = 16

    if target > cpu_limit:
        return cpu_limit
    return target


get_optimal_process_count = decide_process_count


def _process_chunk(tuple args):
    """Worker function for multiprocessing (must be top-level for pickling)."""
    cdef list chunk = args[0]
    cdef bint smart_mode = args[1]
    return process_text('\n'.join(chunk), smart_mode=smart_mode).split('\n')


def process_text_parallel(str text, int num_threads=0, bint smart_mode=True):
    """
    Process text using multiprocessing.Pool (1BRC technique).

    This bypasses the GIL by using separate processes.
    If num_threads is 0 or not specified, automatically decides based on text length.
    """
    if num_threads <= 0:
        num_threads = decide_process_count(text)

    if num_threads < 1:
        num_threads = 1
    if num_threads > 32:
        num_threads = 32

    cdef list lines = text.split('\n')
    cdef Py_ssize_t n = len(lines)

    if n < 100 or num_threads == 1:
        # Not worth parallelizing
        return process_text(text, smart_mode)

    # Split into chunks (like 1BRC's get_parts function)
    chunks = split_lines(lines, num_threads, smart_mode)
    chunk_args = [(chunk, smart_mode) for chunk in chunks]

    # Process in parallel (bypasses GIL)
    with multiprocessing.Pool(num_threads) as pool:
        results = pool.map(_process_chunk, chunk_args)

    # Flatten results (preserving order)
    out = []
    for chunk_result in results:
        out.extend(chunk_result)

    return '\n'.join(out)


def process_file_parallel(str filepath, int num_threads=4, str output=None, bint smart_mode=True):
    """
    1BRC-style parallel file processing.

    Reads file, splits into chunks, processes in parallel, writes output.
    """
    import time
    start = time.perf_counter()

    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found.", file=sys.stderr)
        return ""

    try:
        file_size = os.path.getsize(filepath)

        # Read file (mmap for large files)
        if file_size > 1_000_000:
            try:
                with open(filepath, 'rb') as f:
                    with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                        raw = mm[:]
            except (OSError, ValueError):
                with open(filepath, 'rb') as f:
                    raw = f.read()
        else:
            with open(filepath, 'rb') as f:
                raw = f.read()
    except OSError as e:
        print(f"Error: Could not read file '{filepath}': {e}", file=sys.stderr)
        return ""

    text = raw.decode('utf-8', errors='replace')

    # Process
    if num_threads > 1:
        result = process_text_parallel(text, num_threads, smart_mode)
    else:
        result = process_text(text, smart_mode)

    elapsed = time.perf_counter() - start

    # Output
    if output:
        try:
            with open(output, 'w', encoding='utf-8') as f:
                f.write(result)
        except OSError as e:
            print(f"Error: Could not write output file '{output}': {e}", file=sys.stderr)
    else:
        print(result)

    # Stats
    lines_count = text.count('\n') + 1
    throughput = lines_count / elapsed if elapsed > 0 else 0
    print(f"\n--- Processed {file_size/(1024*1024):.1f}MB | "
          f"{lines_count} lines | {elapsed*1000:.1f}ms | "
          f"{throughput:,.0f} lines/sec | {num_threads} processes ---",
          file=sys.stderr)

    return result


# ══════════════════════════════════════════════════════════════
# SMART MODE: Auto-skip non-Arabic content
# ══════════════════════════════════════════════════════════════

cdef tuple _scan_number(str text, Py_ssize_t i, Py_ssize_t length):
    """Scan numbers, dates, times, percentages, keeping them LTR."""
    cdef Py_ssize_t start = i
    cdef unsigned int cp, next_cp
    if text[i] in ('+', '-') and i + 1 < length:
        next_cp = <unsigned int>ord(text[i+1])
        if _is_digit_cp(next_cp):
            i += 1
    if i < length:
        cp = <unsigned int>ord(text[i])
        if _is_digit_cp(cp):
            while i < length:
                cp = <unsigned int>ord(text[i])
                if _is_digit_cp(cp):
                    i += 1
                elif text[i] in ('.', ',', ':', '/', '-', '_', '\u066B', '\u066C') and i + 1 < length:
                    next_cp = <unsigned int>ord(text[i+1])
                    if _is_digit_cp(next_cp):
                        i += 2
                    else:
                        break
                else:
                    break
            if i < length and text[i] in ('%', '\u066A', '\u2030'):
                i += 1
            return text[start:i], i - start
    return None, 0


cdef str _reverse_arabic_word(str word):
    """
    Reverse an Arabic word preserving Tashkeel (diacritics) on their base chars
    and keeping digit sequences in LTR order.
    """
    if not word:
        return word

    cdef list sub_tokens = []
    cdef str curr_type = ""
    cdef list curr_token = []
    cdef unsigned int cp
    cdef bint is_dig, is_diac
    cdef Py_ssize_t last_idx

    for ch in word:
        cp = <unsigned int>ord(ch)
        is_dig = _is_digit_cp(cp)
        is_diac = _is_diacritic_cp(cp)

        if is_dig:
            if curr_type == "digit":
                curr_token.append(ch)
            else:
                if curr_token:
                    sub_tokens.append((curr_type, curr_token))
                curr_type = "digit"
                curr_token = [ch]
        elif is_diac and curr_type == "letter" and curr_token:
            last_idx = len(curr_token) - 1
            curr_token[last_idx] = curr_token[last_idx] + ch
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

    cdef list res_tokens = []
    for t_type, t_content in sub_tokens:
        if t_type == "digit":
            res_tokens.append("".join(t_content))
        else:
            t_content.reverse()
            res_tokens.append("".join(t_content))

    res_tokens.reverse()
    return "".join(res_tokens)


cdef dict BRACKET_PAIRS = {
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

cdef Py_ssize_t _scan_ansi_escape(str line, Py_ssize_t i, Py_ssize_t length):
    """Scan ANSI escape sequence starting at index i. Returns length of sequence or 0."""
    if i >= length or (line[i] != '\x1b' and line[i] != '\033'):
        return 0
    if i + 1 >= length:
        return 1
    cdef str next_ch = line[i + 1]
    cdef Py_ssize_t end
    cdef unsigned int cp
    if next_ch == '[':
        end = i + 2
        while end < length:
            cp = <unsigned int>ord(line[end])
            if 0x20 <= cp <= 0x3F:
                end += 1
            else:
                break
        if end < length:
            cp = <unsigned int>ord(line[end])
            if 0x40 <= cp <= 0x7E:
                end += 1
        return end - i
    elif next_ch in (']', 'P', '^', '_'):
        end = i + 2
        while end < length:
            if line[end] == '\x07':
                end += 1
                break
            if _starts_with(line, "\x1b\\", end) or _starts_with(line, "\033\\", end):
                end += 2
                break
            end += 1
        return end - i
    else:
        end = i + 1
        while end < length:
            cp = <unsigned int>ord(line[end])
            if 0x20 <= cp <= 0x2F:
                end += 1
            else:
                break
        if end < length:
            cp = <unsigned int>ord(line[end])
            if 0x30 <= cp <= 0x7E:
                end += 1
        return end - i

cdef bint _is_path_start(str line, Py_ssize_t i, Py_ssize_t length):
    """Check if position i starts a file path or URL."""
    if (_starts_with(line, "http://", i) or _starts_with(line, "https://", i) or
        _starts_with(line, "ftp://", i) or _starts_with(line, "file://", i) or
        _starts_with(line, "mailto:", i) or _starts_with(line, "git@", i) or
        _starts_with(line, "ssh://", i) or _starts_with(line, "ws://", i) or
        _starts_with(line, "wss://", i) or _starts_with(line, "sftp://", i) or
        _starts_with(line, "git://", i) or _starts_with(line, "svn://", i)):
        return True
    if (i == 0 or line[i-1] in (' ', '\t', '"', "'", '(', '[', '<', '=', ':', 'm', 'M', ';', 'g')):
        if (_starts_with(line, "/", i) or _starts_with(line, "~/", i) or
            _starts_with(line, "./", i) or _starts_with(line, "../", i) or
            _starts_with(line, "$", i) or _starts_with(line, "%", i)):
            if line[i] == '/' and (i + 1 >= length or line[i+1] in (' ', '\t', '\n', '\r')):
                return False
            return True
        if i + 2 < length and line[i+1] == ':' and line[i+2] in ('\\', '/'):
            if ('A' <= line[i] <= 'Z') or ('a' <= line[i] <= 'z'):
                return True
        if _starts_with(line, ".\\", i) or _starts_with(line, "..\\", i):
            return True
    return False

cdef bint _starts_with(str s, str prefix, Py_ssize_t pos=0):
    """Fast prefix check."""
    cdef Py_ssize_t plen = len(prefix)
    cdef Py_ssize_t slen = len(s)
    if pos + plen > slen:
        return False
    cdef Py_ssize_t i
    for i in range(plen):
        if s[pos + i] != prefix[i]:
            return False
    return True

cdef bint _has_arabic_in_bracket(str line, Py_ssize_t i, Py_ssize_t length):
    cdef str ch = line[i]
    cdef str close_br = BRACKET_PAIRS.get(ch, None)
    if not close_br:
        return False
    cdef Py_ssize_t end = line.find(close_br, i + 1)
    if end != -1:
        return has_arabic(line[i:end+1])
    return False


cdef str _reverse_segment(str segment):
    """Reverse an Arabic segment preserving words, numbers, and mirroring brackets."""
    cdef Py_ssize_t length = len(segment)
    cdef Py_ssize_t i = 0
    cdef list tokens = []
    cdef Py_ssize_t start, num_len
    cdef str ch, num_str, word
    cdef unsigned int cp

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
            num_str, num_len = _scan_number(segment, i, length)
            if num_len > 0:
                tokens.append(num_str)
                i += num_len
            elif ord(ch) in (0x060C, 0x061B, 0x061F, 0x066A, 0x066B, 0x066C):
                tokens.append(ch)
                i += 1
            elif is_arabic_fast(<unsigned int>ord(ch)):
                while i < length and segment[i] not in (' ', '\t', '\n', '\r') and segment[i] not in BRACKET_PAIRS:
                    cp = <unsigned int>ord(segment[i])
                    if _is_digit_cp(cp) or cp in (0x060C, 0x061B, 0x061F, 0x066A, 0x066B, 0x066C):
                        break
                    i += 1
                word = segment[start:i]
                tokens.append(_reverse_arabic_word(word))
            else:
                while i < length and segment[i] not in (' ', '\t', '\n', '\r') and segment[i] not in BRACKET_PAIRS:
                    cp = <unsigned int>ord(segment[i])
                    if is_arabic_fast(cp) or _is_digit_cp(cp) or cp in (0x060C, 0x061B, 0x061F, 0x066A, 0x066B, 0x066C):
                        break
                    i += 1
                tokens.append(segment[start:i])

    tokens.reverse()
    return "".join(tokens)


cdef str _process_line(str line, bint smart_mode=True):
    """Process a single line."""
    if not has_arabic(line):
        return line

    cdef str prefix = ""
    cdef list cells, proc_cells

    if smart_mode:
        for pat in PREFIX_PATTERNS:
            m = pat.match(line)
            if m:
                prefix = m.group(1)
                line = line[len(prefix):]
                break

        if line.startswith("|") and line.endswith("|"):
            cells = line.split("|")
            proc_cells = [_process_line(c, smart_mode=True) for c in cells[1:len(cells)-1]]
            return prefix + "|" + "|".join(proc_cells) + "|"

    cdef Py_ssize_t length = len(line)
    cdef Py_ssize_t i = 0
    cdef list result = []
    cdef Py_ssize_t ansi_len, end, seg_start, last_arabic_i, seg_end, idx
    cdef str ch, trailing, segment
    cdef unsigned int cp, prev_cp
    cdef bint is_br_arabic

    while i < length:
        ansi_len = _scan_ansi_escape(line, i, length)
        if ansi_len > 0:
            result.append(line[i:i+ansi_len])
            i += ansi_len
            continue

        if smart_mode:
            # Skip code blocks (``` ... ```)
            if _starts_with(line, "```", i):
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
        cp = <unsigned int>ord(ch)
        is_br_arabic = (ch in BRACKET_PAIRS) and _has_arabic_in_bracket(line, i, length)
        if is_arabic_fast(cp) or is_br_arabic:
            seg_start = i
            last_arabic_i = i
            while i < length:
                cp = <unsigned int>ord(line[i])
                if is_arabic_fast(cp):
                    last_arabic_i = i
                    i += 1
                elif _scan_ansi_escape(line, i, length) > 0 or (smart_mode and (_starts_with(line, "```", i) or line[i] == '`' or _is_path_start(line, i, length))):
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
                        prev_cp = <unsigned int>ord(line[seg_end - 1])
                        if line[seg_end - 1] in (' ', '\t'):
                            seg_end -= 1
                        elif line[seg_end - 1] in BRACKET_PAIRS or line[seg_end - 1] in ('.', ',', '!', '?', ':', ';', '-'):
                            break
                        elif _is_digit_cp(prev_cp):
                            break
                        else:
                            break

            i = seg_end
            segment = line[seg_start:seg_end]
            result.append(_reverse_segment(segment))
        else:
            result.append(line[i])
            i += 1

    return prefix + "".join(result)


def process_text(str text, bint smart_mode=True):
    """
    Process Arabic prose for correct display in LTR terminals.
    If smart_mode is True, auto-skips code blocks, URLs, paths, commands.
    Tracks multiline code blocks across lines.
    """
    cdef list lines = text.split('\n')
    cdef list out = []
    cdef bint in_code_block = False
    cdef str line, stripped

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
                    out.append(_process_line(line, smart_mode=True))
        else:
            out.append(_process_line(line, smart_mode=False))
    return '\n'.join(out)


# Alias for backward compatibility & README matching
reverse_arabic_text = process_text


