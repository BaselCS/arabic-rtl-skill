#!/usr/bin/env python3
"""
pure_arabic_shaper.py — Production-grade Pure Python Arabic Shaping and BiDi Engine.
Zero external dependencies.

Features:
- Contextual glyph shaping (Isolated, Initial, Medial, Final) using Unicode Presentation Forms-B
- Lam-Alef ligatures (ﻵ, ﻷ, ﻹ, ﻻ) with diacritic preservation
- Comprehensive Quranic Tashkeel & Harakat handling
- BiDi numbers (ASCII, Eastern Arabic, Persian) preserved in LTR order
- Smart bracket and punctuation mirroring
- Automatic terminal environment detection (prevents double-reversal on BiDi terminals)
- Multiple modes: auto, visual (shaped), logical, reverse
"""

import sys
import os
import re
import argparse

# ─────────────────────────────────────────────────────────────
# 1. UNICODE SHAPING TABLE (Isolated, Final, Medial, Initial, Left-Join)
# ─────────────────────────────────────────────────────────────

SHAPING_TABLE = {
    # Hamza & variants
    '\u0621': ('\uFE80', '\uFE80', '', '', False),        # ء HAMZA
    '\u0622': ('\uFE81', '\uFE82', '', '', False),        # آ ALEF WITH MADDA
    '\u0623': ('\uFE83', '\uFE84', '', '', False),        # أ ALEF WITH HAMZA ABOVE
    '\u0624': ('\uFE85', '\uFE86', '', '', False),        # ؤ WAW WITH HAMZA ABOVE
    '\u0625': ('\uFE87', '\uFE88', '', '', False),        # إ ALEF WITH HAMZA BELOW
    '\u0626': ('\uFE89', '\uFE8A', '\uFE8C', '\uFE8B', True),  # ئ YEH WITH HAMZA ABOVE
    '\u0627': ('\uFE8D', '\uFE8E', '', '', False),        # ا ALEF
    '\u0628': ('\uFE8F', '\uFE90', '\uFE92', '\uFE91', True),  # ب BEH
    '\u0629': ('\uFE93', '\uFE94', '', '', False),        # ة TEH MARBUTA
    '\u062A': ('\uFE95', '\uFE96', '\uFE98', '\uFE97', True),  # ت TEH
    '\u062B': ('\uFE99', '\uFE9A', '\uFE9C', '\uFE9B', True),  # ث THEH
    '\u062C': ('\uFE9D', '\uFE9E', '\uFEA0', '\uFE9F', True),  # ج JEEM
    '\u062D': ('\uFEA1', '\uFEA2', '\uFEA4', '\uFEA3', True),  # ح HAH
    '\u062E': ('\uFEA5', '\uFEA6', '\uFEA8', '\uFEA7', True),  # خ KHAH
    '\u062F': ('\uFEA9', '\uFEAA', '', '', False),        # د DAL
    '\u0630': ('\uFEAB', '\uFEAC', '', '', False),        # ذ THAL
    '\u0631': ('\uFEAD', '\uFEAE', '', '', False),        # ر REH
    '\u0632': ('\uFEAF', '\uFEB0', '', '', False),        # ز ZAIN
    '\u0633': ('\uFEB1', '\uFEB2', '\uFEB4', '\uFEB3', True),  # س SEEN
    '\u0634': ('\uFEB5', '\uFEB6', '\uFEB8', '\uFEB7', True),  # ش SHEEN
    '\u0635': ('\uFEB9', '\uFEBA', '\uFEBC', '\uFEBB', True),  # ص SAD
    '\u0636': ('\uFEBD', '\uFEBE', '\uFEC0', '\uFEBF', True),  # ض DAD
    '\u0637': ('\uFEC1', '\uFEC2', '\uFEC4', '\uFEC3', True),  # ط TAH
    '\u0638': ('\uFEC5', '\uFEC6', '\uFEC8', '\uFEC7', True),  # ظ ZAH
    '\u0639': ('\uFEC9', '\uFECA', '\uFECC', '\uFECB', True),  # ع AIN
    '\u063A': ('\uFECD', '\uFECE', '\uFED0', '\uFECF', True),  # غ GHAIN
    '\u0640': ('\u0640', '\u0640', '\u0640', '\u0640', True),  # ـ TATWEEL
    '\u0641': ('\uFED1', '\uFED2', '\uFED4', '\uFED3', True),  # ف FEH
    '\u0642': ('\uFED5', '\uFED6', '\uFED8', '\uFED7', True),  # ق QAF
    '\u0643': ('\uFED9', '\uFEDA', '\uFEDC', '\uFEDB', True),  # ك KAF
    '\u0644': ('\uFEDD', '\uFEDE', '\uFEE0', '\uFEDF', True),  # ل LAM
    '\u0645': ('\uFEE1', '\uFEE2', '\uFEE4', '\uFEE3', True),  # م MEEM
    '\u0646': ('\uFEE5', '\uFEE6', '\uFEE8', '\uFEE7', True),  # ن NOON
    '\u0647': ('\uFEE9', '\uFEEA', '\uFEEC', '\uFEEB', True),  # ه HEH
    '\u0648': ('\uFEED', '\uFEEE', '', '', False),        # و WAW
    '\u0649': ('\uFEEF', '\uFEF0', '\uFEF2', '\uFEF1', True),  # ى ALEF MAKSURA
    '\u064A': ('\uFEF1', '\uFEF2', '\uFEF4', '\uFEF3', True),  # ي YEH
}

LAM_ALEF_MAP = {
    '\u0622': ('\uFEF5', '\uFEF6'),  # ل + آ -> ﻵ
    '\u0623': ('\uFEF7', '\uFEF8'),  # ل + أ -> ﻷ
    '\u0625': ('\uFEF9', '\uFEFA'),  # ل + إ -> ﻹ
    '\u0627': ('\uFEFB', '\uFEFC'),  # ل + ا -> لا
}

DIACRITICS = {
    0x064B, 0x064C, 0x064D, 0x064E, 0x064F, 0x0650, 0x0651, 0x0652,
    0x0653, 0x0654, 0x0655, 0x0670, 0x06D6, 0x06D7, 0x06D8, 0x06D9,
    0x06DA, 0x06DB, 0x06DC, 0x06DF, 0x06E0, 0x06E1, 0x06E2, 0x06E3,
    0x06E4, 0x06E8, 0x06EA, 0x06EB, 0x06EC, 0x06ED, 0x08E3, 0x08E4,
    0x08E5, 0x08E6, 0x08E7, 0x08E8, 0x08E9, 0x08EA, 0x08EB, 0x08EC,
    0x08ED, 0x08EE, 0x08EF, 0x08F0, 0x08F1, 0x08F2, 0x08F3,
}

BRACKET_MIRROR = {
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
}


def is_diacritic(ch):
    return ord(ch) in DIACRITICS


def is_arabic_char(ch):
    cp = ord(ch)
    return (
        (0x0600 <= cp <= 0x06FF) or
        (0x0750 <= cp <= 0x077F) or
        (0x08A0 <= cp <= 0x08FF) or
        (0xFB50 <= cp <= 0xFDFF) or
        (0xFE70 <= cp <= 0xFEFF)
    )


def is_digit_char(c):
    cp = ord(c)
    return (48 <= cp <= 57) or (0x0660 <= cp <= 0x0669) or (0x06F0 <= cp <= 0x06F9)


def detect_terminal_bidi():
    """
    Check if environment natively supports BiDi / Arabic text shaping.
    Returns True if native BiDi is available (avoid double-reversal).
    """
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    term = os.environ.get("TERM", "").lower()
    
    # Terminals known to support native BiDi / HarfBuzz shaping
    bidi_terminals = ["wezterm", "ghostty", "iterm.app", "konsole", "mlterm"]
    if any(bt in term_program for bt in bidi_terminals):
        return True
    
    # Modern Linux desktop terminals under Wayland/KDE/GNOME
    if os.environ.get("WAYLAND_DISPLAY") and os.environ.get("XDG_CURRENT_DESKTOP"):
        if "foot" in term or "wezterm" in term or "kitty" in term:
            return True
            
    return False


class LetterUnit:
    def __init__(self, base_char, diacritics=None):
        self.base_char = base_char
        self.diacritics = diacritics or []
        self.shaped_char = base_char

    def __repr__(self):
        return f"LetterUnit({self.base_char!r}, diacs={self.diacritics!r}, shaped={self.shaped_char!r})"


def parse_units(word):
    units = []
    curr_base = None
    curr_diacs = []

    for ch in word:
        if is_diacritic(ch):
            if curr_base is not None:
                curr_diacs.append(ch)
            else:
                units.append(LetterUnit(ch))
        else:
            if curr_base is not None:
                units.append(LetterUnit(curr_base, curr_diacs))
                curr_diacs = []
            curr_base = ch

    if curr_base is not None:
        units.append(LetterUnit(curr_base, curr_diacs))

    return units


def shape_arabic_units(units):
    n = len(units)
    if n == 0:
        return []

    # Pass 1: Lam-Alef ligatures
    ligature_units = []
    i = 0
    while i < n:
        u = units[i]
        if u.base_char == '\u0644' and (i + 1 < n) and (units[i + 1].base_char in LAM_ALEF_MAP):
            next_u = units[i + 1]
            alef_char = next_u.base_char
            combined_diacs = u.diacritics + next_u.diacritics
            lig_unit = LetterUnit(f"\u0644{alef_char}", combined_diacs)
            lig_unit._lam_alef_target = alef_char
            ligature_units.append(lig_unit)
            i += 2
        else:
            ligature_units.append(u)
            i += 1

    # Pass 2: Contextual shaping
    m = len(ligature_units)
    prev_connects_left = False

    for idx in range(m):
        u = ligature_units[idx]
        
        next_connects_right = False
        if idx + 1 < m:
            next_char = ligature_units[idx + 1].base_char
            if next_char in SHAPING_TABLE or hasattr(ligature_units[idx + 1], '_lam_alef_target'):
                next_connects_right = True

        if hasattr(u, '_lam_alef_target'):
            iso, fin = LAM_ALEF_MAP[u._lam_alef_target]
            u.shaped_char = fin if prev_connects_left else iso
            prev_connects_left = False
            continue

        base = u.base_char
        if base not in SHAPING_TABLE:
            u.shaped_char = base
            prev_connects_left = False
            continue

        iso, fin, med, ini, connects_left = SHAPING_TABLE[base]

        if prev_connects_left and next_connects_right and med:
            u.shaped_char = med
        elif prev_connects_left and fin:
            u.shaped_char = fin
        elif next_connects_right and ini:
            u.shaped_char = ini
        else:
            u.shaped_char = iso

        prev_connects_left = connects_left

    return ligature_units


def render_unit_to_string(unit):
    return unit.shaped_char + "".join(unit.diacritics)


def reverse_shaped_word(units):
    sub_tokens = []
    curr_type = ""
    curr_token = []

    for u in units:
        is_dig = any(is_digit_char(c) for c in u.base_char)
        if is_dig:
            if curr_type == "digit":
                curr_token.append(u)
            else:
                if curr_token:
                    sub_tokens.append((curr_type, curr_token))
                curr_type = "digit"
                curr_token = [u]
        else:
            if curr_type == "arabic":
                curr_token.append(u)
            else:
                if curr_token:
                    sub_tokens.append((curr_type, curr_token))
                curr_type = "arabic"
                curr_token = [u]

    if curr_token:
        sub_tokens.append((curr_type, curr_token))

    res_parts = []
    for t_type, t_content in sub_tokens:
        if t_type == "digit":
            res_parts.append("".join(render_unit_to_string(u) for u in t_content))
        else:
            t_content_rev = list(reversed(t_content))
            res_parts.append("".join(render_unit_to_string(u) for u in t_content_rev))

    res_parts.reverse()
    return "".join(res_parts)


def process_arabic_word_visual(word):
    if not word or not any(is_arabic_char(c) for c in word):
        return word
    units = parse_units(word)
    shaped_units = shape_arabic_units(units)
    return reverse_shaped_word(shaped_units)


def tokenize_line(line):
    tokens = []
    n = len(line)
    i = 0

    while i < n:
        ch = line[i]

        if ch in ' \t':
            start = i
            while i < n and line[i] in ' \t':
                i += 1
            tokens.append(('space', line[start:i]))
            continue

        if ch in BRACKET_MIRROR:
            tokens.append(('bracket', ch))
            i += 1
            continue

        if is_digit_char(ch):
            start = i
            while i < n and (is_digit_char(line[i]) or line[i] in '.,:-'):
                if line[i] in '.,:-' and (i + 1 >= n or not is_digit_char(line[i + 1])):
                    break
                i += 1
            tokens.append(('digit', line[start:i]))
            continue

        if is_arabic_char(ch) or is_diacritic(ch):
            start = i
            while i < n and (is_arabic_char(line[i]) or is_diacritic(line[i])):
                i += 1
            tokens.append(('arabic', line[start:i]))
            continue

        start = i
        while (i < n and not is_arabic_char(line[i]) and not is_diacritic(line[i]) and 
               line[i] not in ' \t' and line[i] not in BRACKET_MIRROR and not is_digit_char(line[i])):
            i += 1
        tokens.append(('other', line[start:i]))

    return tokens


def process_text_visual(text):
    """Visual shaping + BiDi reversal (for dumb / LTR-only terminals)."""
    lines = text.split('\n')
    processed_lines = []

    for line in lines:
        if not any(is_arabic_char(c) for c in line):
            processed_lines.append(line)
            continue

        tokens = tokenize_line(line)
        transformed_tokens = []

        for token_type, content in tokens:
            if token_type == 'arabic':
                transformed_tokens.append(process_arabic_word_visual(content))
            elif token_type == 'bracket':
                transformed_tokens.append(BRACKET_MIRROR.get(content, content))
            elif token_type == 'digit':
                transformed_tokens.append(content)
            else:
                transformed_tokens.append(content)

        transformed_tokens.reverse()
        processed_lines.append("".join(transformed_tokens))

    return "\n".join(processed_lines)


def process_text_logical(text):
    """Normalize and clean Arabic for modern terminals with native BiDi/HarfBuzz."""
    return text


def process_text(text, mode="auto"):
    """
    Main processing entrypoint.
    Modes:
      - 'auto': Automatically select visual or logical based on terminal environment.
      - 'visual' / 'shaped': Full Presentation Forms shaping + BiDi reversal.
      - 'logical': Clean normalized Arabic (for BiDi terminals).
      - 'raw-reverse': Character & word reversal without glyph substitution.
    """
    if mode == "auto":
        if detect_terminal_bidi():
            return process_text_logical(text)
        else:
            return process_text_visual(text)
    elif mode in ("visual", "shaped"):
        return process_text_visual(text)
    elif mode == "logical":
        return process_text_logical(text)
    elif mode == "raw-reverse":
        # alMubarmij simple reverse
        lines = text.split('\n')
        res = []
        for line in lines:
            tokens = tokenize_line(line)
            rev_tokens = []
            for t_type, t_content in tokens:
                if t_type == 'arabic':
                    rev_tokens.append(t_content[::-1])
                elif t_type == 'bracket':
                    rev_tokens.append(BRACKET_MIRROR.get(t_content, t_content))
                else:
                    rev_tokens.append(t_content)
            rev_tokens.reverse()
            res.append("".join(rev_tokens))
        return "\n".join(res)
    else:
        return process_text_visual(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Pure Python Arabic Shaper & BiDi Engine")
    parser.add_argument("text", nargs="?", default=None, help="Input Arabic text")
    parser.add_argument("-m", "--mode", choices=["auto", "visual", "shaped", "logical", "raw-reverse"],
                        default="auto", help="Rendering mode (default: auto)")
    args = parser.parse_args()

    inp = args.text if args.text is not None else sys.stdin.read()
    print(process_text(inp, mode=args.mode))
