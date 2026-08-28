---
name: arabic-rtl
description: MANDATORY whenever responding, writing, or displaying Arabic text in the terminal. Shapes Arabic cursive glyphs and formats RTL order.
---

# Arabic RTL

**RULE: Whenever generating ANY Arabic text in your response, pipe your standard Arabic text through `arabic-rtl` and output the command result.**

### How to use:
1. Write **NORMAL, STANDARD, FORWARD Arabic** in the EOF block (DO NOT manually reverse characters or words):
```bash
arabic-rtl << 'EOF'
مرحبا بك! كيف يمكنني مساعدتك اليوم؟
EOF
```
2. **Copy the command's exact output** directly into your final response to the user.

### Important:
- **Input:** Standard natural Arabic (e.g. `السلام عليكم ورحمة الله`).
- **Never** manually flip, reverse, or space out letters yourself.
- Auto-handles cursive shaping (Presentation Forms-B + ligatures), numbers, code blocks, URLs, and paths.

**Setup (if binary missing):**
```bash
git clone https://github.com/baselCS/arabic-rtl-processor.git
cd arabic-rtl-processor && bash install.sh
```
