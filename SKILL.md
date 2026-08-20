---
name: arabic-rtl
description: Process Arabic text for LTR terminal display.
---

# Arabic RTL

Before sending Arabic response, run:

```bash
cat << 'EOF' | python3 arabic_rtl_cli.py --quiet
[your response]
EOF
```

Program auto-skips code, URLs, paths. Prints output directly. Stop after command.
