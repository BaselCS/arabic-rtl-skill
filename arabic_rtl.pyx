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

# ══════════════════════════════════════════════════════════════
# 1BRC TECHNIQUE 1: Fast Bitmaps & Direct Lookup Tables
# ══════════════════════════════════════════════════════════════

cdef unsigned char ARABIC_BITMAP[8192]     # 65536 bits for Arabic char detection
cdef unsigned char DIACRITIC_BITMAP[8192]  # 65536 bits for diacritics detection
cdef unsigned short BRACKET_MIRROR_LUT[65536]  # Direct 16-bit bracket mirror table

cdef void init_bitmaps_and_luts() noexcept nogil:
    """Initialize all bitmaps and lookup tables once at startup."""
    cdef unsigned int ch
    cdef unsigned int byte_idx, bit_idx
    cdef int i

    for i in range(8192):
        ARABIC_BITMAP[i] = 0
        DIACRITIC_BITMAP[i] = 0

    for i in range(65536):
        BRACKET_MIRROR_LUT[i] = 0

    # Arabic BMP ranges
    for ch in range(0x0600, 0x0700):
        ARABIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    for ch in range(0x0750, 0x0780):
        ARABIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    for ch in range(0x0870, 0x0900):
        ARABIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    for ch in range(0xFB50, 0xFE00):
        ARABIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    for ch in range(0xFE70, 0xFF00):
        ARABIC_BITMAP[ch >> 3] |= (1 << (ch & 7))

    ch = 0x060C; ARABIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    ch = 0x061B; ARABIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    ch = 0x061F; ARABIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    ch = 0x0640; ARABIC_BITMAP[ch >> 3] |= (1 << (ch & 7))

    # Diacritics
    for ch in range(0x064B, 0x0660):
        DIACRITIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    ch = 0x0670; DIACRITIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    for ch in range(0x06D6, 0x06EE):
        DIACRITIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    for ch in range(0x08E3, 0x0900):
        DIACRITIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    for ch in range(0x0610, 0x061B):
        DIACRITIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    for ch in range(0x0898, 0x08A0):
        DIACRITIC_BITMAP[ch >> 3] |= (1 << (ch & 7))
    for ch in range(0xFE70, 0xFE80, 2):
        DIACRITIC_BITMAP[ch >> 3] |= (1 << (ch & 7))

    # Bracket pairs
    BRACKET_MIRROR_LUT[0x0028] = 0x0029; BRACKET_MIRROR_LUT[0x0029] = 0x0028  # ()
    BRACKET_MIRROR_LUT[0x005B] = 0x005D; BRACKET_MIRROR_LUT[0x005D] = 0x005B  # []
    BRACKET_MIRROR_LUT[0x007B] = 0x007D; BRACKET_MIRROR_LUT[0x007D] = 0x007B  # {}
    BRACKET_MIRROR_LUT[0x003C] = 0x003E; BRACKET_MIRROR_LUT[0x003E] = 0x003C  # <>
    BRACKET_MIRROR_LUT[0x00AB] = 0x00BB; BRACKET_MIRROR_LUT[0x00BB] = 0x00AB  # «»
    BRACKET_MIRROR_LUT[0x2039] = 0x203A; BRACKET_MIRROR_LUT[0x203A] = 0x2039  # ‹›
    BRACKET_MIRROR_LUT[0xFF08] = 0xFF09; BRACKET_MIRROR_LUT[0xFF09] = 0xFF08  # （）
    BRACKET_MIRROR_LUT[0xFD3E] = 0xFD3F; BRACKET_MIRROR_LUT[0xFD3F] = 0xFD3E  # ﴿﴾
    BRACKET_MIRROR_LUT[0x201C] = 0x201D; BRACKET_MIRROR_LUT[0x201D] = 0x201C  # “”
    BRACKET_MIRROR_LUT[0x2018] = 0x2019; BRACKET_MIRROR_LUT[0x2019] = 0x2018  # ‘’
    BRACKET_MIRROR_LUT[0x2985] = 0x2986; BRACKET_MIRROR_LUT[0x2986] = 0x2985  # ⦅⦆
    BRACKET_MIRROR_LUT[0x27E6] = 0x27E7; BRACKET_MIRROR_LUT[0x27E7] = 0x27E6  # ⟦⟧
    BRACKET_MIRROR_LUT[0x27E8] = 0x27E9; BRACKET_MIRROR_LUT[0x27E9] = 0x27E8  # ⟨⟩
    BRACKET_MIRROR_LUT[0x3010] = 0x3011; BRACKET_MIRROR_LUT[0x3011] = 0x3010  # 【】
    BRACKET_MIRROR_LUT[0x3014] = 0x3015; BRACKET_MIRROR_LUT[0x3015] = 0x3014  # 〔〕
    BRACKET_MIRROR_LUT[0x3016] = 0x3017; BRACKET_MIRROR_LUT[0x3017] = 0x3016  # 〖〗
    BRACKET_MIRROR_LUT[0x2045] = 0x2046; BRACKET_MIRROR_LUT[0x2046] = 0x2045  # ⁅⁆


cdef inline bint is_arabic_fast(unsigned int ch) noexcept nogil:
    """O(1) Arabic character check using bitmap lookup."""
    if ch > 0xFFFF:
        return (0x10EC0 <= ch <= 0x10EFF) or (0x1EE00 <= ch <= 0x1EEFF)
    return (ARABIC_BITMAP[ch >> 3] >> (ch & 7)) & 1


cdef inline bint _is_digit_cp(unsigned int cp) noexcept nogil:
    return (48 <= cp <= 57) or (0x0660 <= cp <= 0x0669) or (0x06F0 <= cp <= 0x06F9)


cdef inline bint _is_diacritic_cp(unsigned int cp) noexcept nogil:
    if cp > 0xFFFF:
        return False
    return (DIACRITIC_BITMAP[cp >> 3] >> (cp & 7)) & 1


cdef inline unsigned short get_bracket_mirror_fast(unsigned int cp) noexcept nogil:
    if cp > 0xFFFF:
        return 0
    return BRACKET_MIRROR_LUT[cp]


init_bitmaps_and_luts()

cdef list PREFIX_PATTERNS = [
    re.compile(r'^(#{1,6}\s+)'),
    re.compile(r'^(>\s*(?:\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*)?)'),
    re.compile(r'^(>+\s*)'),
    re.compile(r'^(\s*[-*+]\s+\[[ xX]\]\s+)'),
    re.compile(r'^(\s*[-*+]\s+)'),
    re.compile(r'^(\s*\d+[.)]\s+)'),
    re.compile(r'^(\s*[$#]\s+)'),
]

# ══════════════════════════════════════════════════════════════
# Contextual Shaping Tables (Unicode Presentation Forms-B & A)
# ══════════════════════════════════════════════════════════════

cdef struct ShapeEntry:
    unsigned int iso
    unsigned int fin
    unsigned int med
    unsigned int ini
    bint connects_left
    bint is_valid

cdef ShapeEntry SHAPING_TABLE[256]

cdef void init_shaping_table() noexcept nogil:
    cdef int i
    for i in range(256):
        SHAPING_TABLE[i].iso = 0
        SHAPING_TABLE[i].fin = 0
        SHAPING_TABLE[i].med = 0
        SHAPING_TABLE[i].ini = 0
        SHAPING_TABLE[i].connects_left = False
        SHAPING_TABLE[i].is_valid = False

    SHAPING_TABLE[0x21] = ShapeEntry(0xFE80, 0xFE80, 0, 0, False, True)        # ء
    SHAPING_TABLE[0x22] = ShapeEntry(0xFE81, 0xFE82, 0, 0, False, True)        # آ
    SHAPING_TABLE[0x23] = ShapeEntry(0xFE83, 0xFE84, 0, 0, False, True)        # أ
    SHAPING_TABLE[0x24] = ShapeEntry(0xFE85, 0xFE86, 0, 0, False, True)        # ؤ
    SHAPING_TABLE[0x25] = ShapeEntry(0xFE87, 0xFE88, 0, 0, False, True)        # إ
    SHAPING_TABLE[0x26] = ShapeEntry(0xFE89, 0xFE8A, 0xFE8C, 0xFE8B, True, True)  # ئ
    SHAPING_TABLE[0x27] = ShapeEntry(0xFE8D, 0xFE8E, 0, 0, False, True)        # ا
    SHAPING_TABLE[0x28] = ShapeEntry(0xFE8F, 0xFE90, 0xFE92, 0xFE91, True, True)  # ب
    SHAPING_TABLE[0x29] = ShapeEntry(0xFE93, 0xFE94, 0, 0, False, True)        # ة
    SHAPING_TABLE[0x2A] = ShapeEntry(0xFE95, 0xFE96, 0xFE98, 0xFE97, True, True)  # ت
    SHAPING_TABLE[0x2B] = ShapeEntry(0xFE99, 0xFE9A, 0xFE9C, 0xFE9B, True, True)  # ث
    SHAPING_TABLE[0x2C] = ShapeEntry(0xFE9D, 0xFE9E, 0xFEA0, 0xFE9F, True, True)  # ج
    SHAPING_TABLE[0x2D] = ShapeEntry(0xFEA1, 0xFEA2, 0xFEA4, 0xFEA3, True, True)  # ح
    SHAPING_TABLE[0x2E] = ShapeEntry(0xFEA5, 0xFEA6, 0xFEA8, 0xFEA7, True, True)  # خ
    SHAPING_TABLE[0x2F] = ShapeEntry(0xFEA9, 0xFEAA, 0, 0, False, True)        # د
    SHAPING_TABLE[0x30] = ShapeEntry(0xFEAB, 0xFEAC, 0, 0, False, True)        # ذ
    SHAPING_TABLE[0x31] = ShapeEntry(0xFEAD, 0xFEAE, 0, 0, False, True)        # ر
    SHAPING_TABLE[0x32] = ShapeEntry(0xFEAF, 0xFEB0, 0, 0, False, True)        # ز
    SHAPING_TABLE[0x33] = ShapeEntry(0xFEB1, 0xFEB2, 0xFEB4, 0xFEB3, True, True)  # س
    SHAPING_TABLE[0x34] = ShapeEntry(0xFEB5, 0xFEB6, 0xFEB8, 0xFEB7, True, True)  # ش
    SHAPING_TABLE[0x35] = ShapeEntry(0xFEB9, 0xFEBA, 0xFEBC, 0xFEBB, True, True)  # ص
    SHAPING_TABLE[0x36] = ShapeEntry(0xFEBD, 0xFEBE, 0xFEC0, 0xFEBF, True, True)  # ض
    SHAPING_TABLE[0x37] = ShapeEntry(0xFEC1, 0xFEC2, 0xFEC4, 0xFEC3, True, True)  # ط
    SHAPING_TABLE[0x38] = ShapeEntry(0xFEC5, 0xFEC6, 0xFEC8, 0xFEC7, True, True)  # ظ
    SHAPING_TABLE[0x39] = ShapeEntry(0xFEC9, 0xFECA, 0xFECC, 0xFECB, True, True)  # ع
    SHAPING_TABLE[0x3A] = ShapeEntry(0xFECD, 0xFECE, 0xFED0, 0xFECF, True, True)  # غ
    SHAPING_TABLE[0x40] = ShapeEntry(0x0640, 0x0640, 0x0640, 0x0640, True, True)  # ـ TATWEEL
    SHAPING_TABLE[0x41] = ShapeEntry(0xFED1, 0xFED2, 0xFED4, 0xFED3, True, True)  # ف
    SHAPING_TABLE[0x42] = ShapeEntry(0xFED5, 0xFED6, 0xFED8, 0xFED7, True, True)  # ق
    SHAPING_TABLE[0x43] = ShapeEntry(0xFED9, 0xFEDA, 0xFEDC, 0xFEDB, True, True)  # ك
    SHAPING_TABLE[0x44] = ShapeEntry(0xFEDD, 0xFEDE, 0xFEE0, 0xFEDF, True, True)  # ل
    SHAPING_TABLE[0x45] = ShapeEntry(0xFEE1, 0xFEE2, 0xFEE4, 0xFEE3, True, True)  # م
    SHAPING_TABLE[0x46] = ShapeEntry(0xFEE5, 0xFEE6, 0xFEE8, 0xFEE7, True, True)  # ن
    SHAPING_TABLE[0x47] = ShapeEntry(0xFEE9, 0xFEEA, 0xFEEC, 0xFEEB, True, True)  # ه
    SHAPING_TABLE[0x48] = ShapeEntry(0xFEED, 0xFEEE, 0, 0, False, True)        # و
    SHAPING_TABLE[0x49] = ShapeEntry(0xFEEF, 0xFEF0, 0xFEF4, 0xFEF3, True, True)  # ى
    SHAPING_TABLE[0x4A] = ShapeEntry(0xFEF1, 0xFEF2, 0xFEF4, 0xFEF3, True, True)  # ي

    # Extended Arabic (Quranic, Persian, Urdu)
    SHAPING_TABLE[0x71] = ShapeEntry(0xFB50, 0xFB51, 0, 0, False, True)        # ٱ ALEF WASLA
    SHAPING_TABLE[0x79] = ShapeEntry(0xFB66, 0xFB67, 0xFB69, 0xFB68, True, True)  # ٹ TTEH
    SHAPING_TABLE[0x7E] = ShapeEntry(0xFB56, 0xFB57, 0xFB59, 0xFB58, True, True)  # پ PEH
    SHAPING_TABLE[0x86] = ShapeEntry(0xFB7A, 0xFB7B, 0xFB7D, 0xFB7C, True, True)  # چ TCHEH
    SHAPING_TABLE[0x88] = ShapeEntry(0xFB88, 0xFB89, 0, 0, False, True)        # ڈ DDAL
    SHAPING_TABLE[0x91] = ShapeEntry(0xFB8C, 0xFB8D, 0, 0, False, True)        # ڑ RREH
    SHAPING_TABLE[0x98] = ShapeEntry(0xFB8A, 0xFB8B, 0, 0, False, True)        # ژ JEH
    SHAPING_TABLE[0xAF] = ShapeEntry(0xFB92, 0xFB93, 0xFB95, 0xFB94, True, True)  # گ GAF
    SHAPING_TABLE[0xBA] = ShapeEntry(0xFB9E, 0xFB9F, 0, 0, False, True)        # ں NOON GHUNNA
    SHAPING_TABLE[0xCC] = ShapeEntry(0xFBFC, 0xFBFD, 0xFBFF, 0xFBFE, True, True)  # ی FARSI YEH
    SHAPING_TABLE[0xD2] = ShapeEntry(0xFBAE, 0xFBAF, 0, 0, False, True)        # ے YEH BARREE

init_shaping_table()


cdef inline bint _is_lam_alef(unsigned int lam_cp, unsigned int alef_cp, unsigned int *iso_out, unsigned int *fin_out) noexcept nogil:
    if lam_cp != 0x0644:
        return False
    if alef_cp == 0x0622:
        iso_out[0] = 0xFEF5
        fin_out[0] = 0xFEF6
        return True
    elif alef_cp == 0x0623:
        iso_out[0] = 0xFEF7
        fin_out[0] = 0xFEF8
        return True
    elif alef_cp == 0x0625:
        iso_out[0] = 0xFEF9
        fin_out[0] = 0xFEFA
        return True
    elif alef_cp == 0x0627:
        iso_out[0] = 0xFEFB
        fin_out[0] = 0xFEFC
        return True
    elif alef_cp == 0x0671:
        iso_out[0] = 0xFEFB
        fin_out[0] = 0xFEFC
        return True
    return False


cdef struct FastUnit:
    unsigned int base_cp
    unsigned int shaped_cp
    unsigned int diacs[8]
    unsigned char diac_count
    unsigned int lam_alef_iso
    unsigned int lam_alef_fin


cdef int shape_and_reverse_word_c(
    const unsigned int *word_cps,
    int word_len,
    unsigned int *out_cps,
    bint shape
) noexcept nogil:
    """
    100% pure C stack-allocated shaping and reversal.
    Zero Python heap allocation, 100% cache-local.
    """
    if word_len <= 0:
        return 0

    cdef FastUnit raw_units[512]
    cdef int raw_count = 0
    cdef unsigned int cp
    cdef int i, j, k
    cdef int out_pos = 0
    cdef int seg_start = 0
    cdef bint is_cur_dig = False
    cdef bint is_dig = False
    cdef int tok_starts[256]
    cdef int tok_lens[256]
    cdef bint tok_is_dig[256]
    cdef int num_toks = 0
    cdef FastUnit lig_units[512]
    cdef int lig_count = 0
    cdef unsigned int iso_la, fin_la
    cdef bint prev_connects_left = False
    cdef bint next_connects_right = False
    cdef ShapeEntry *entry = NULL
    cdef ShapeEntry *next_entry = NULL

    for i in range(word_len):
        cp = word_cps[i]
        if _is_diacritic_cp(cp):
            if raw_count > 0 and raw_units[raw_count - 1].diac_count < 8:
                raw_units[raw_count - 1].diacs[raw_units[raw_count - 1].diac_count] = cp
                raw_units[raw_count - 1].diac_count += 1
            elif raw_count < 512:
                raw_units[raw_count].base_cp = cp
                raw_units[raw_count].shaped_cp = cp
                raw_units[raw_count].diacs[0] = cp
                raw_units[raw_count].diac_count = 1
                raw_units[raw_count].lam_alef_iso = 0
                raw_units[raw_count].lam_alef_fin = 0
                raw_count += 1
        elif raw_count < 512:
            raw_units[raw_count].base_cp = cp
            raw_units[raw_count].shaped_cp = cp
            raw_units[raw_count].diac_count = 0
            raw_units[raw_count].lam_alef_iso = 0
            raw_units[raw_count].lam_alef_fin = 0
            raw_count += 1

    if not shape:
        i = 0
        while i < raw_count:
            is_dig = _is_digit_cp(raw_units[i].base_cp)
            seg_start = i
            while i < raw_count and _is_digit_cp(raw_units[i].base_cp) == is_dig:
                i += 1
            if num_toks < 256:
                tok_starts[num_toks] = seg_start
                tok_lens[num_toks] = i - seg_start
                tok_is_dig[num_toks] = is_dig
                num_toks += 1

        for k in range(num_toks - 1, -1, -1):
            seg_start = tok_starts[k]
            if tok_is_dig[k]:
                for i in range(seg_start, seg_start + tok_lens[k]):
                    out_cps[out_pos] = raw_units[i].base_cp
                    out_pos += 1
                    for j in range(raw_units[i].diac_count):
                        out_cps[out_pos] = raw_units[i].diacs[j]
                        out_pos += 1
            else:
                for i in range(seg_start + tok_lens[k] - 1, seg_start - 1, -1):
                    out_cps[out_pos] = raw_units[i].base_cp
                    out_pos += 1
                    for j in range(raw_units[i].diac_count):
                        out_cps[out_pos] = raw_units[i].diacs[j]
                        out_pos += 1
        return out_pos

    # Pass 1: Lam-Alef ligatures
    i = 0
    while i < raw_count:
        if raw_units[i].base_cp == 0x0644 and (i + 1 < raw_count) and (lig_count < 512):
            if _is_lam_alef(raw_units[i].base_cp, raw_units[i + 1].base_cp, &iso_la, &fin_la):
                lig_units[lig_count].base_cp = raw_units[i].base_cp
                lig_units[lig_count].shaped_cp = iso_la
                lig_units[lig_count].lam_alef_iso = iso_la
                lig_units[lig_count].lam_alef_fin = fin_la
                lig_units[lig_count].diac_count = 0
                for j in range(raw_units[i].diac_count):
                    if lig_units[lig_count].diac_count < 8:
                        lig_units[lig_count].diacs[lig_units[lig_count].diac_count] = raw_units[i].diacs[j]
                        lig_units[lig_count].diac_count += 1
                for j in range(raw_units[i + 1].diac_count):
                    if lig_units[lig_count].diac_count < 8:
                        lig_units[lig_count].diacs[lig_units[lig_count].diac_count] = raw_units[i + 1].diacs[j]
                        lig_units[lig_count].diac_count += 1
                lig_count += 1
                i += 2
                continue
        if lig_count < 512:
            lig_units[lig_count] = raw_units[i]
            lig_count += 1
        i += 1

    # Pass 2: Contextual shaping
    prev_connects_left = False

    for i in range(lig_count):
        next_connects_right = False
        if i + 1 < lig_count:
            if lig_units[i + 1].lam_alef_iso != 0:
                next_connects_right = True
            elif 0x0600 <= lig_units[i + 1].base_cp <= 0x06FF:
                next_entry = &SHAPING_TABLE[lig_units[i + 1].base_cp - 0x0600]
                if next_entry.is_valid:
                    next_connects_right = True

        if lig_units[i].lam_alef_iso != 0:
            lig_units[i].shaped_cp = lig_units[i].lam_alef_fin if prev_connects_left else lig_units[i].lam_alef_iso
            prev_connects_left = False
            continue

        cp = lig_units[i].base_cp
        if 0x0600 <= cp <= 0x06FF:
            entry = &SHAPING_TABLE[cp - 0x0600]
            if entry.is_valid:
                if prev_connects_left and next_connects_right and entry.med != 0:
                    lig_units[i].shaped_cp = entry.med
                elif prev_connects_left and entry.fin != 0:
                    lig_units[i].shaped_cp = entry.fin
                elif next_connects_right and entry.ini != 0:
                    lig_units[i].shaped_cp = entry.ini
                else:
                    lig_units[i].shaped_cp = entry.iso
                prev_connects_left = entry.connects_left
            else:
                lig_units[i].shaped_cp = cp
                prev_connects_left = False
        else:
            lig_units[i].shaped_cp = cp
            prev_connects_left = False

    # Pass 3: Reverse shaped units preserving LTR digits
    out_pos = 0
    num_toks = 0

    i = 0
    while i < lig_count:
        is_dig = _is_digit_cp(lig_units[i].base_cp)
        seg_start = i
        while i < lig_count and _is_digit_cp(lig_units[i].base_cp) == is_dig:
            i += 1
        if num_toks < 256:
            tok_starts[num_toks] = seg_start
            tok_lens[num_toks] = i - seg_start
            tok_is_dig[num_toks] = is_dig
            num_toks += 1

    for k in range(num_toks - 1, -1, -1):
        seg_start = tok_starts[k]
        if tok_is_dig[k]:
            for i in range(seg_start, seg_start + tok_lens[k]):
                out_cps[out_pos] = lig_units[i].shaped_cp
                out_pos += 1
                for j in range(lig_units[i].diac_count):
                    out_cps[out_pos] = lig_units[i].diacs[j]
                    out_pos += 1
        else:
            for i in range(seg_start + tok_lens[k] - 1, seg_start - 1, -1):
                out_cps[out_pos] = lig_units[i].shaped_cp
                out_pos += 1
                for j in range(lig_units[i].diac_count):
                    out_cps[out_pos] = lig_units[i].diacs[j]
                    out_pos += 1

    return out_pos


cdef str _reverse_arabic_word(str word, bint shape=True):
    """Bridge for Python callers."""
    cdef Py_ssize_t length = len(word)
    if length == 0:
        return ""
    cdef unsigned int in_buf[512]
    cdef unsigned int out_buf[1024]
    cdef Py_ssize_t i
    for i in range(min(length, 512)):
        in_buf[i] = <unsigned int>ord(word[i])
    cdef int out_len = shape_and_reverse_word_c(in_buf, min(<int>length, 512), out_buf, shape)
    return "".join([chr(out_buf[i]) for i in range(out_len)])


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


cdef str _reverse_segment(str segment, bint shape=True):
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
                tokens.append(_reverse_arabic_word(word, shape=shape))
            else:
                while i < length and segment[i] not in (' ', '\t', '\n', '\r') and segment[i] not in BRACKET_PAIRS:
                    cp = <unsigned int>ord(segment[i])
                    if is_arabic_fast(cp) or _is_digit_cp(cp) or cp in (0x060C, 0x061B, 0x061F, 0x066A, 0x066B, 0x066C):
                        break
                    i += 1
                tokens.append(segment[start:i])

    tokens.reverse()
    return "".join(tokens)


cdef str _process_line(str line, bint smart_mode=True, bint shape=True):
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
            proc_cells = [_process_line(c, smart_mode=True, shape=shape) for c in cells[1:len(cells)-1]]
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
            result.append(_reverse_segment(segment, shape=shape))
        else:
            result.append(line[i])
            i += 1

    return prefix + "".join(result)


def process_text(str text, bint smart_mode=True, bint shape=True):
    """
    Process Arabic prose for correct display in LTR terminals.
    If smart_mode is True, auto-skips code blocks, URLs, paths, commands.
    If shape is True, performs contextual shaping (Unicode Presentation Forms-B).
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
                    out.append(_process_line(line, smart_mode=True, shape=shape))
        else:
            out.append(_process_line(line, smart_mode=False, shape=shape))
    return '\n'.join(out)


# Alias for backward compatibility & README matching
reverse_arabic_text = process_text


def process_batch(list texts, int num_threads=4, bint smart_mode=True, bint shape=True):
    """Process multiple strings."""
    cdef Py_ssize_t n = len(texts)
    cdef list results = [None] * n
    cdef Py_ssize_t i
    for i in range(n):
        results[i] = process_text(texts[i], smart_mode, shape)
    return results


def _process_chunk(tuple args):
    """Worker function for multiprocessing (must be top-level for pickling)."""
    cdef list chunk = args[0]
    cdef bint smart_mode = args[1]
    cdef bint shape = args[2] if len(args) > 2 else True
    return process_text('\n'.join(chunk), smart_mode=smart_mode, shape=shape).split('\n')


def process_text_parallel(str text, int num_threads=0, bint smart_mode=True, bint shape=True):
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
        return process_text(text, smart_mode, shape)

    chunks = split_lines(lines, num_threads, smart_mode)
    chunk_args = [(chunk, smart_mode, shape) for chunk in chunks]

    with multiprocessing.Pool(num_threads) as pool:
        results = pool.map(_process_chunk, chunk_args)

    out = []
    for chunk_result in results:
        out.extend(chunk_result)

    return '\n'.join(out)


def process_file_parallel(str filepath, int num_threads=4, str output=None, bint smart_mode=True, bint shape=True):
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

    if num_threads > 1:
        result = process_text_parallel(text, num_threads, smart_mode, shape)
    else:
        result = process_text(text, smart_mode, shape)

    elapsed = time.perf_counter() - start

    if output:
        try:
            with open(output, 'w', encoding='utf-8') as f:
                f.write(result)
        except OSError as e:
            print(f"Error: Could not write output file '{output}': {e}", file=sys.stderr)
    else:
        print(result)

    lines_count = text.count('\n') + 1
    throughput = lines_count / elapsed if elapsed > 0 else 0
    print(f"\n--- Processed {file_size/(1024*1024):.1f}MB | "
          f"{lines_count} lines | {elapsed*1000:.1f}ms | "
          f"{throughput:,.0f} lines/sec | {num_threads} processes ---",
          file=sys.stderr)

    return result


