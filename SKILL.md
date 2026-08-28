---
name: arabic-rtl
description: MANDATORY whenever responding, writing, or displaying Arabic text in the terminal. Shapes Arabic cursive glyphs and formats RTL order.
---

# Arabic RTL

**RULE: Whenever generating ANY Arabic text in your response, pipe your standard Arabic text through `arabic-rtl` and output the command result.**

### How to use:
1. Write **NORMAL, STANDARD, FORWARD Arabic** in the EOF block (plain Arabic or with Tashkeel/Quranic diacritics):
```bash
arabic-rtl << 'EOF'
مرحبا بك! كيف يمكنني مساعدتك اليوم؟
EOF
```
2. **Copy the command's exact output** directly into your final response to the user.

### Key Capabilities:
- **Cursive Shaping:** Auto-converts to Presentation Forms-B and Lam-Alef ligatures (`لا`, `لأ`, `لإ`, `لآ`).
- **Tashkeel & Diacritics:** Keeps multi-stacked diacritics attached to base letters without breaking cursive connections.
- **Smart Skipping:** Preserves markdown code blocks (` ``` ` / ` ` `), URLs, file paths, and LTR numbers.
- **Never** manually flip, reverse, or space out letters yourself.

**Setup (if binary missing):**
```bash
git clone https://github.com/baselCS/arabic-rtl-processor.git
cd arabic-rtl-processor && bash install.sh
```
