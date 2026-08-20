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
        return False
    return (ARABIC_BITMAP[ch >> 3] >> (ch & 7)) & 1


# Initialize on module load
init_arabic_bitmap()


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


def _process_chunk(tuple args):
    """Worker function for multiprocessing (must be top-level for pickling)."""
    cdef list chunk = args[0]
    cdef bint smart_mode = args[1]
    if smart_mode:
        return process_text('\n'.join(chunk), smart_mode=True).split('\n')
    else:
        return [_process_line_normal(line) for line in chunk]


def process_text_parallel(str text, int num_threads=4, bint smart_mode=True):
    """
    Process text using multiprocessing.Pool (1BRC technique).

    This bypasses the GIL by using separate processes.
    """
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

cdef str _reverse_arabic_word(str word):
    """
    Reverse an Arabic word preserving Tashkeel (diacritics) on their base chars
    and keeping digit sequences (ASCII 0-9, Arabic ٠-٩, Persian ۰-۹) in LTR order.
    """
    if not word:
        return word

    cdef list sub_tokens = []
    cdef str curr_type = ""
    cdef list curr_token = []
    cdef unsigned int cp
    cdef bint is_dig, is_diac

    for ch in word:
        cp = <unsigned int>ord(ch)
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

cdef str _reverse_segment(str segment):
    """Reverse an Arabic segment preserving words, numbers, and mirroring brackets."""
    cdef list tokens = []
    cdef Py_ssize_t seg_i = 0
    cdef Py_ssize_t seg_len = len(segment)
    cdef Py_ssize_t start
    cdef unsigned int cp, c
    cdef bint is_digit
    cdef str ch, word

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
            cp = <unsigned int>ord(ch)
            is_digit = (48 <= cp <= 57) or (0x0660 <= cp <= 0x0669) or (0x06F0 <= cp <= 0x06F9)
            if is_digit:
                while seg_i < seg_len:
                    c = <unsigned int>ord(segment[seg_i])
                    if (48 <= c <= 57) or (0x0660 <= c <= 0x0669) or (0x06F0 <= c <= 0x06F9):
                        seg_i += 1
                    else:
                        break
                tokens.append(segment[start:seg_i])
            elif cp in (0x060C, 0x061B, 0x061F, 0x066A, 0x066B, 0x066C):
                tokens.append(ch)
                seg_i += 1
            elif is_arabic_fast(cp):
                while seg_i < seg_len and segment[seg_i] not in (' ', '\n', '\r') and segment[seg_i] not in BRACKET_PAIRS:
                    c = <unsigned int>ord(segment[seg_i])
                    if (48 <= c <= 57) or (0x0660 <= c <= 0x0669) or (0x06F0 <= c <= 0x06F9) or c in (0x060C, 0x061B, 0x061F, 0x066A, 0x066B, 0x066C):
                        break
                    seg_i += 1
                word = segment[start:seg_i]
                tokens.append(_reverse_arabic_word(word))
            else:
                while seg_i < seg_len and segment[seg_i] not in (' ', '\n', '\r') and segment[seg_i] not in BRACKET_PAIRS:
                    c = <unsigned int>ord(segment[seg_i])
                    if is_arabic_fast(c):
                        break
                    seg_i += 1
                tokens.append(segment[start:seg_i])

    tokens.reverse()
    return "".join(tokens)

cdef str _smart_process_line(str line):
    """Process a line, skipping code blocks, URLs, paths, commands, and ANSI escape sequences."""
    cdef Py_ssize_t length = len(line)
    cdef Py_ssize_t i = 0
    cdef Py_ssize_t end
    cdef str result = ""
    cdef str segment
    cdef Py_ssize_t seg_start, seg_end, last_arabic_i, ansi_len
    cdef unsigned int ch, prev_ch

    while i < length:
        # Skip ANSI escape sequences
        ansi_len = _scan_ansi_escape(line, i, length)
        if ansi_len > 0:
            result += line[i:i+ansi_len]
            i += ansi_len
            continue

        # Skip code blocks (``` ... ```)
        if _starts_with(line, "```", i):
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

        # Skip URLs and File paths
        if _is_path_start(line, i, length):
            end = i
            while end < length and line[end] not in (' ', '\t', '\n', '\r', '"', "'", ')', ']', '>'):
                end += 1
            result += line[i:end]
            i = end
            continue

        # Process this character normally
        ch = <unsigned int>ord(line[i])
        if is_arabic_fast(ch):
            # Find Arabic segment boundary
            seg_start = i
            last_arabic_i = i
            while i < length:
                ch = <unsigned int>ord(line[i])
                if is_arabic_fast(ch):
                    last_arabic_i = i
                    i += 1
                elif _scan_ansi_escape(line, i, length) > 0 or _is_path_start(line, i, length) or _starts_with(line, "```", i) or line[i] == '`':
                    break
                elif line[i] in ('\n', '\r'):
                    break
                else:
                    i += 1
            seg_end = i
            while seg_end > last_arabic_i + 1:
                prev_ch = <unsigned int>ord(line[seg_end - 1])
                if line[seg_end - 1] in (' ', '\t'):
                    seg_end -= 1
                elif line[seg_end - 1] in BRACKET_PAIRS or line[seg_end - 1] in ('.', ',', '!', '?', ':', ';', '-'):
                    break
                elif (48 <= prev_ch <= 57) or (0x0660 <= prev_ch <= 0x0669) or (0x06F0 <= prev_ch <= 0x06F9):
                    break
                else:
                    seg_end -= 1

            i = seg_end
            segment = line[seg_start:seg_end]
            result += _reverse_segment(segment)
        else:
            result += line[i]
            i += 1

    return result


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


cdef str _process_line_normal(str line):
    """Process a line without smart skipping."""
    cdef Py_ssize_t length = len(line)
    cdef Py_ssize_t i = 0
    cdef str result = ""
    cdef str segment
    cdef Py_ssize_t seg_start, seg_end, last_arabic_i, ansi_len
    cdef unsigned int ch

    while i < length:
        # Skip ANSI escape sequences
        ansi_len = _scan_ansi_escape(line, i, length)
        if ansi_len > 0:
            result += line[i:i+ansi_len]
            i += ansi_len
            continue

        ch = <unsigned int>ord(line[i])
        if is_arabic_fast(ch):
            seg_start = i
            last_arabic_i = i
            while i < length:
                ch = <unsigned int>ord(line[i])
                if is_arabic_fast(ch):
                    last_arabic_i = i
                elif _scan_ansi_escape(line, i, length) > 0 or line[i] in ('\n', '\r'):
                    break
                i += 1
            seg_end = last_arabic_i + 1
            i = seg_end
            segment = line[seg_start:seg_end]
            result += _reverse_segment(segment)
        else:
            result += line[i]
            i += 1

    return result


def process_text(str text, bint smart_mode=True):
    """
    Process Arabic prose.
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
                    out.append(_smart_process_line(line))
                    if stripped.count("```") % 2 != 0:
                        in_code_block = True
                else:
                    out.append(_smart_process_line(line))
        else:
            out.append(_process_line_normal(line))
    return '\n'.join(out)


# Alias for backward compatibility & README matching
reverse_arabic_text = process_text


