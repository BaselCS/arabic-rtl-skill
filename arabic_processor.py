#!/usr/bin/env python3
"""
arabic_processor.py — Robust Arabic RTL & Cursive Shaping Processor
═════════════════════════════════════════════════════════════════════
Converts logical Arabic text for correct connected cursive display
in Left-to-Right (LTR) monospace terminal emulators (Ghostty, Alacritty, Kitty, Windows Terminal).

Uses:
  • arabic_reshaper: Contextual cursive glyph substitution (Presentation Forms-B)
  • python-bidi (bidi.algorithm): Unicode Bidirectional Algorithm (UBA) reordering
"""

import sys
import os
import re
import argparse
from typing import Optional, List

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:
    print(
        "Error: Missing required dependencies.\n"
        "Install them using:\n"
        "    uv pip install arabic-reshaper python-bidi\n"
        "    or\n"
        "    pip install arabic-reshaper python-bidi",
        file=sys.stderr
    )
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════
# Configuration & Constants
# ══════════════════════════════════════════════════════════════════

ARABIC_CHAR_PATTERN = re.compile(
    r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]'
)

URL_OR_PATH_PATTERN = re.compile(
    r'^(https?://|ftp://|file://|ssh://|git@|/|~/|\./|\.\./|[A-Za-z]:[\\/])'
)

PREFIX_PATTERNS = [
    re.compile(r'^(#+\s+)'),           # Markdown headers (#, ##, ###)
    re.compile(r'^(\s*[-*+]\s+\[[ xX]\]\s+)'), # Task checkboxes (- [ ])
    re.compile(r'^(\s*[-*+]\s+)'),     # Bullet points
    re.compile(r'^(\s*\d+[\.\)]\s+)'), # Numbered lists (1. , 1) )
    re.compile(r'^(\s*>\s*)'),         # Blockquotes
    re.compile(r'^([$#>]\s+)'),        # Shell prompts
]


def create_reshaper(delete_harakat: bool = True, support_ligatures: bool = True) -> arabic_reshaper.ArabicReshaper:
    """Create and configure ArabicReshaper with production defaults."""
    config = {
        'delete_harakat': delete_harakat,
        'support_ligatures': support_ligatures,
        'support_tatweel': True,
        'use_unshaped_instead_of_isolated': False,
    }
    return arabic_reshaper.ArabicReshaper(configuration=config)


# ══════════════════════════════════════════════════════════════════
# Core Processing Logic
# ══════════════════════════════════════════════════════════════════

class ArabicProcessor:
    """Handles contextual shaping and BiDi reordering for terminal display."""

    def __init__(self, delete_harakat: bool = True, support_ligatures: bool = True):
        self.reshaper = create_reshaper(
            delete_harakat=delete_harakat,
            support_ligatures=support_ligatures
        )

    def has_arabic(self, text: str) -> bool:
        """Check if string contains any Arabic characters."""
        return bool(ARABIC_CHAR_PATTERN.search(text))

    def process_segment(self, segment: str, base_dir: Optional[str] = None) -> str:
        """Shape Arabic glyphs and apply BiDi visual reordering."""
        if not self.has_arabic(segment):
            return segment

        # Step 1: Contextual Shaping (Converts to Presentation Forms-B & Ligatures)
        reshaped = self.reshaper.reshape(segment)

        # Step 2: Unicode Bidirectional Algorithm (Visual LTR run order)
        return get_display(reshaped, base_dir=base_dir)

    def process_line(self, line: str, smart_mode: bool = True) -> str:
        """Process a single line with smart code/URL/path preservation."""
        if not self.has_arabic(line):
            return line

        prefix = ""
        if smart_mode:
            # Preserve line prefixes (markdown bullets, headers, shell prompts)
            for pat in PREFIX_PATTERNS:
                m = pat.match(line)
                if m:
                    prefix = m.group(1)
                    line = line[len(prefix):]
                    break

            # Handle Markdown table row (| col1 | col2 |)
            if line.startswith("|") and line.endswith("|"):
                cells = line.split("|")
                proc_cells = [self.process_line(c, smart_mode=True) for c in cells[1:-1]]
                return prefix + "|" + "|".join(proc_cells) + "|"

        length = len(line)
        i = 0
        result: List[str] = []

        while i < length:
            if smart_mode:
                # Skip fenced code blocks (``` ... ```)
                if line.startswith("```", i):
                    end = line.find("```", i + 3)
                    if end == -1:
                        result.append(line[i:])
                        break
                    result.append(line[i:end + 3])
                    i = end + 3
                    continue

                # Skip inline code (` ... `)
                if line[i] == '`':
                    end = line.find('`', i + 1)
                    if end == -1:
                        result.append(line[i:])
                        break
                    result.append(line[i:end + 1])
                    i = end + 1
                    continue

                # Skip URLs and File paths
                if URL_OR_PATH_PATTERN.match(line[i:]):
                    end = i
                    while end < length and line[end] not in (' ', '\t', '\n', '\r', '"', "'", ')', ']', '>'):
                        end += 1
                    result.append(line[i:end])
                    i = end
                    continue

            # Process Arabic segments
            if self.has_arabic(line[i]):
                seg_start = i
                last_ar_idx = i
                while i < length:
                    if self.has_arabic(line[i]):
                        last_ar_idx = i
                        i += 1
                    elif smart_mode and (line.startswith("```", i) or line[i] == '`' or URL_OR_PATH_PATTERN.match(line[i:])):
                        break
                    elif line[i] in ('\n', '\r'):
                        break
                    else:
                        i += 1

                seg_end = i
                trailing = line[last_ar_idx + 1:seg_end]
                if "  " in trailing:
                    idx = trailing.find("  ")
                    seg_end = last_ar_idx + 1 + idx
                else:
                    while seg_end > last_ar_idx + 1:
                        if line[seg_end - 1] in (' ', '\t'):
                            seg_end -= 1
                        elif line[seg_end - 1].isdigit() or line[seg_end - 1] in ('(', ')', '[', ']', '{', '}', '.', ',', '!', '?', ':', ';', '-'):
                            break
                        else:
                            break

                i = seg_end
                segment = line[seg_start:seg_end]
                result.append(self.process_segment(segment))
            else:
                result.append(line[i])
                i += 1

        return prefix + "".join(result)

    def process_text(self, text: str, smart_mode: bool = True) -> str:
        """Process full multiline text block."""
        lines = text.split('\n')
        out: List[str] = []
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
                        out.append(self.process_line(line, smart_mode=True))
            else:
                out.append(self.process_line(line, smart_mode=False))

        return '\n'.join(out)


# ══════════════════════════════════════════════════════════════════
# CLI Entrypoint
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='Production Arabic RTL & Cursive Shaping Processor for LTR Terminals'
    )
    parser.add_argument('text', nargs='?', help='Arabic text to process')
    parser.add_argument('--file', '-f', help='Input file path')
    parser.add_argument('--output', '-o', help='Output file path (default: stdout)')
    parser.add_argument('--stream', '-S', action='store_true', help='Stream line-by-line in real time (for tail -f)')
    parser.add_argument('--keep-tashkeel', '-kt', action='store_true', help='Keep Tashkeel / diacritics (default: stripped for monospace alignment)')
    parser.add_argument('--no-smart', action='store_true', help='Disable smart mode (processes code/URLs as normal text)')
    args = parser.parse_args()

    processor = ArabicProcessor(
        delete_harakat=not args.keep_tashkeel,
        support_ligatures=True
    )
    smart_mode = not args.no_smart

    # Stream mode: process stdin line-by-line in real time
    if args.stream:
        try:
            for line in sys.stdin:
                if line.endswith('\n'):
                    sys.stdout.write(processor.process_line(line[:-1], smart_mode=smart_mode) + '\n')
                else:
                    sys.stdout.write(processor.process_line(line, smart_mode=smart_mode))
                sys.stdout.flush()
        except KeyboardInterrupt:
            pass
        return

    # File processing mode
    if args.file:
        if not os.path.exists(args.file):
            print(f"Error: File '{args.file}' not found.", file=sys.stderr)
            sys.exit(1)
        with open(args.file, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        result = processor.process_text(content, smart_mode=smart_mode)
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(result)
        else:
            print(result)
        return

    # Direct text input or stdin pipe
    if args.text:
        text = args.text
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        parser.print_help()
        return

    result = processor.process_text(text, smart_mode=smart_mode)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result)
    else:
        print(result)


if __name__ == '__main__':
    main()
