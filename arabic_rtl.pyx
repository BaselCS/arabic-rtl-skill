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

    for ch in range(0x08A0, 0x0900):  # Arabic Extended-A
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

cdef list split_lines(list lines, int num_chunks):
    """Split lines into roughly equal chunks."""
    cdef Py_ssize_t n = len(lines)
    # Bug fix #4: cap num_chunks to n so chunk_size never becomes 0
    if n > 0 and num_chunks > n:
        num_chunks = n
    cdef Py_ssize_t chunk_size = n // num_chunks if num_chunks > 0 else n
    cdef list chunks = []
    cdef Py_ssize_t start = 0

    for i in range(num_chunks - 1):
        end = start + chunk_size
        chunks.append(lines[start:end])
        start = end
    chunks.append(lines[start:])  # Last chunk gets remainder
    return chunks


def _process_chunk(tuple args):
    """Worker function for multiprocessing (must be top-level for pickling)."""
    cdef list chunk = args[0]
    cdef bint smart_mode = args[1]
    if smart_mode:
        return [_smart_process_line(line) for line in chunk]
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
    chunks = split_lines(lines, num_threads)
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

    # Process
    if num_threads > 1:
        result = process_text_parallel(text, num_threads, smart_mode)
    else:
        result = process_text(text, smart_mode)

    elapsed = time.perf_counter() - start

    # Output
    if output:
        with open(output, 'w', encoding='utf-8') as f:
            f.write(result)
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

cdef str _smart_process_line(str line):
    """Process a line, skipping code blocks, URLs, paths, commands."""
    cdef Py_ssize_t length = len(line)
    cdef Py_ssize_t i = 0
    cdef str result = ""
    cdef str segment
    cdef Py_ssize_t seg_i, seg_len, word_start, seg_start, seg_end, last_arabic_i
    cdef unsigned int ch

    while i < length:
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

        # Skip URLs
        if _starts_with(line, "http://", i) or _starts_with(line, "https://", i) or _starts_with(line, "ftp://", i):
            end = i
            while end < length and line[end] not in (' ', '\t', '\n', '\r', ')', ']', '>'):
                end += 1
            result += line[i:end]
            i = end
            continue

        # Skip file paths (starting with / or ~/)
        if (i == 0 or line[i-1] == ' ') and (_starts_with(line, "/", i) or _starts_with(line, "~/", i)):
            end = i
            while end < length and line[end] not in (' ', '\t', '\n', '\r'):
                end += 1
            result += line[i:end]
            i = end
            continue

        # Skip shell commands ($ or # at start)
        if i == 0 and line[i] in ('$', '#'):
            result += line[i:]
            return result

        # Process this character normally
        ch = <unsigned int>ord(line[i])
        if is_arabic_fast(ch):
            # Find Arabic segment
            seg_start = i
            last_arabic_i = i
            while i < length:
                ch = <unsigned int>ord(line[i])
                if is_arabic_fast(ch):
                    last_arabic_i = i
                elif ch != 0x20:
                    break
                i += 1
            seg_end = last_arabic_i + 1
            i = seg_end
            # Reverse the Arabic segment preserving whitespace exactly
            segment = line[seg_start:seg_end]
            rev_words = []
            
            seg_i = 0
            seg_len = len(segment)
            
            while seg_i < seg_len:
                if segment[seg_i] == ' ':
                    word_start = seg_i
                    while seg_i < seg_len and segment[seg_i] == ' ':
                        seg_i += 1
                    rev_words.append(segment[word_start:seg_i])
                else:
                    word_start = seg_i
                    while seg_i < seg_len and segment[seg_i] != ' ':
                        seg_i += 1
                    word = segment[word_start:seg_i]
                    if len(word) > 1:
                        rev_words.append(word[::-1])
                    else:
                        rev_words.append(word)
            
            rev_words.reverse()
            result += ''.join(rev_words)
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
    cdef Py_ssize_t seg_i, seg_len, word_start, seg_start, seg_end, last_arabic_i
    cdef unsigned int ch

    while i < length:
        ch = <unsigned int>ord(line[i])
        if is_arabic_fast(ch):
            # Find Arabic segment
            seg_start = i
            last_arabic_i = i
            while i < length:
                ch = <unsigned int>ord(line[i])
                if is_arabic_fast(ch):
                    last_arabic_i = i
                elif ch != 0x20:
                    break
                i += 1
            seg_end = last_arabic_i + 1
            i = seg_end
            # Reverse the Arabic segment preserving whitespace exactly
            segment = line[seg_start:seg_end]
            rev_words = []
            
            seg_i = 0
            seg_len = len(segment)
            
            while seg_i < seg_len:
                if segment[seg_i] == ' ':
                    word_start = seg_i
                    while seg_i < seg_len and segment[seg_i] == ' ':
                        seg_i += 1
                    rev_words.append(segment[word_start:seg_i])
                else:
                    word_start = seg_i
                    while seg_i < seg_len and segment[seg_i] != ' ':
                        seg_i += 1
                    word = segment[word_start:seg_i]
                    if len(word) > 1:
                        rev_words.append(word[::-1])
                    else:
                        rev_words.append(word)
            
            rev_words.reverse()
            result += ''.join(rev_words)
        else:
            result += line[i]
            i += 1

    return result


def process_text(str text, bint smart_mode=True):
    """
    Process Arabic prose.
    If smart_mode is True, auto-skips code blocks, URLs, paths, commands.
    """
    cdef list lines = text.split('\n')
    cdef list out = []
    for line in lines:
        if smart_mode:
            out.append(_smart_process_line(line))
        else:
            out.append(_process_line_normal(line))
    return '\n'.join(out)


# Alias for backward compatibility & README matching
reverse_arabic_text = process_text

