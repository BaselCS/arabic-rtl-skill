---
name: arabic-rtl
description: Process Arabic text for LTR terminal display. Use for ALL Arabic output.
---

# Arabic RTL Processor

## Purpose

Convert Arabic text so it displays correctly in left-to-right terminals.

## How It Works

A compiled native processor at `/home/basel/Work/python/arabic_rtl_fast/arabic_rtl_cli.py` handles everything:
- Reverses Arabic character order inside each word
- Reverses word order of each line
- Auto-skips code blocks, URLs, file paths, shell commands
- Leaves English, numbers, and non-Arabic content untouched

## Required Workflow

Before sending ANY response containing Arabic text:

```bash
echo "FULL_RESPONSE" | python3 /home/basel/Work/python/arabic_rtl_fast/arabic_rtl_cli.py --quiet
```

That's it. The program handles all detection and processing.

## What It Skips Automatically

- Code blocks (``` ... ```)
- URLs (http://, https://, ftp://)
- File paths (/path/to/file, ~/path)
- Shell commands ($ or # at start)
- English text and numbers

## What It Processes

- All Arabic prose
- Arabic in headings, bullets, questions
- Inline Arabic phrases
- Single Arabic words

## Rules

- Pipe your ENTIRE response through the program
- Do NOT manually reverse Arabic text
- Do NOT explain this process unless asked
- Do NOT output normal Arabic when this skill is active

## Quick Test

```bash
echo "الحمد لله رب العالمين" | python3 /home/basel/Work/python/arabic_rtl_fast/arabic_rtl_cli.py --quiet
```

Expected: `نيملاعلا بر هلل دمحلا`
