---
name: arabic-rtl
description: Process Arabic text for LTR terminal display. Use for ALL Arabic output.
---

# Arabic RTL Processor

## Purpose

Convert Arabic text so it displays correctly in left-to-right terminals.

## How It Works

A compiled native processor handles everything automatically.

## Installation (One-time)

```bash
# Clone and build
git clone https://github.com/baselCS/arabic-rtl-processor.git
cd arabic-rtl-processor
pip install cython
python3 setup.py build_ext --inplace

# Add to PATH (optional, for easier access)
echo 'export PATH="$PWD:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## Required Workflow

Before sending ANY response containing Arabic text, run this command and STOP:

```bash
cat << 'EOF' | python3 arabic_rtl_cli.py --quiet
[your full response here]
EOF
```

**If not in PATH**, use full path:
```bash
cat << 'EOF' | /full/path/to/arabic-rtl-processor/arabic_rtl_cli.py --quiet
[your full response here]
EOF
```

The program prints the transformed output directly to the user. Your job is done after running the command.

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
- Do NOT echo or repeat the output — the program handles it

## Quick Test

```bash
echo "الحمد لله رب العالمين" | python3 arabic_rtl_cli.py --quiet
```

Expected: `نيملاعلا بر هلل دمحلا`
