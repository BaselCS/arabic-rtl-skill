import pytest
import subprocess
import sys
import tempfile
import os
from arabic_processor import ArabicProcessor

@pytest.fixture
def processor():
    return ArabicProcessor(delete_harakat=True, support_ligatures=True)

def test_pure_arabic(processor):
    text = "السلام عليكم ورحمة الله"
    result = processor.process_text(text)
    assert "ﻡﻼﺴﻟﺍ" in result
    assert "ﷲ" in result

def test_mixed_arabic_english_numbers(processor):
    text = "Hello world مرحبا بالعالم 2026"
    result = processor.process_text(text)
    assert "Hello world" in result
    assert "2026" in result
    assert "ﺎﺒﺣﺮﻣ" in result

def test_paths_and_urls_preserved(processor):
    text = "راجع المسار /home/user/work وموقع https://google.com الآن"
    result = processor.process_text(text)
    assert "/home/user/work" in result
    assert "https://google.com" in result

def test_code_blocks_skipped(processor):
    text = (
        "نص توضيحي:\n"
        "```python\n"
        "# comment\n"
        "x = 10\n"
        "```\n"
        "تم بحمد الله"
    )
    result = processor.process_text(text, smart_mode=True)
    assert "```python\n# comment\nx = 10\n```" in result
    assert "ﷲ ﺪﻤﺤﺑ ﻢﺗ" in result

def test_cli_execution():
    cmd = [sys.executable, "arabic_processor.py", "بسم الله الرحمن الرحيم"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "ﻢﻴﺣﺮﻟﺍ" in res.stdout
    assert "ﷲ" in res.stdout

def test_cli_file_io():
    with tempfile.NamedTemporaryFile('w+', encoding='utf-8', delete=False) as f_in:
        f_in.write("الحمد لله رب العالمين\n")
        in_path = f_in.name
    out_path = in_path + ".out"

    try:
        cmd = [sys.executable, "arabic_processor.py", "-f", in_path, "-o", out_path]
        subprocess.run(cmd, check=True)
        with open(out_path, 'r', encoding='utf-8') as f_out:
            content = f_out.read()
        assert "نﻴﻤﻟﺎﻌﻟﺍ" in content or "ﻦﻴﻤﻟﺎﻌﻟﺍ" in content
        assert "ﺪﻤﺤﻟﺍ" in content
    finally:
        if os.path.exists(in_path):
            os.remove(in_path)
        if os.path.exists(out_path):
            os.remove(out_path)
