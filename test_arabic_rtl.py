import pytest
import tempfile
import os
import sys
import subprocess

import arabic_rtl
import arabic_rtl_cli
import arabic_rtl_daemon


def test_has_arabic():
    assert arabic_rtl.has_arabic("مرحبا") is True
    assert arabic_rtl.has_arabic("Hello World") is False
    assert arabic_rtl.has_arabic("Hello مرحبا World") is True
    assert arabic_rtl_cli.py_has_arabic("مرحبا") is True
    assert arabic_rtl_cli.py_has_arabic("Hello World") is False


def test_basic_reversal():
    inp = "الحمد لله"
    expected = "ﻪﻠﻟ ﺪﻤﺤﻟﺍ"
    assert arabic_rtl.process_text(inp) == expected
    assert arabic_rtl.reverse_arabic_text(inp) == expected
    assert arabic_rtl_cli.py_process_text(inp) == expected
    assert arabic_rtl_cli.reverse_arabic_text(inp) == expected

    # Test raw reversal mode (shape=False)
    expected_raw = "هلل دمحلا"
    assert arabic_rtl.process_text(inp, shape=False) == expected_raw
    assert arabic_rtl_cli.py_process_text(inp, shape=False) == expected_raw


def test_spaces_preservation():
    # Test spaces between Arabic words and trailing spaces before non-Arabic text
    inp = "مرحبا      world"
    expected = "ﺎﺒﺣﺮﻣ      world"
    assert arabic_rtl.process_text(inp) == expected
    assert arabic_rtl_cli.py_process_text(inp) == expected

    inp2 = "  مرحبا  علي  "
    expected2 = "  ﻲﻠﻋ  ﺎﺒﺣﺮﻣ  "
    assert arabic_rtl.process_text(inp2) == expected2
    assert arabic_rtl_cli.py_process_text(inp2) == expected2


def test_smart_mode_skipping():
    # Code blocks
    inp = "مرحبا ```code``` عالم"
    expected = "ﺎﺒﺣﺮﻣ ```code``` ﻢﻟﺎﻋ"
    assert arabic_rtl.process_text(inp) == expected
    assert arabic_rtl_cli.py_process_text(inp) == expected

    # Inline code
    inp_inline = "مرحبا `var_name` عالم"
    expected_inline = "ﺎﺒﺣﺮﻣ `var_name` ﻢﻟﺎﻋ"
    assert arabic_rtl.process_text(inp_inline) == expected_inline
    assert arabic_rtl_cli.py_process_text(inp_inline) == expected_inline

    # URLs
    inp_url = "مرحبا https://example.com/test عالم"
    expected_url = "ﺎﺒﺣﺮﻣ https://example.com/test ﻢﻟﺎﻋ"
    assert arabic_rtl.process_text(inp_url) == expected_url
    assert arabic_rtl_cli.py_process_text(inp_url) == expected_url

    # Paths
    inp_path = "مرحبا /usr/local/bin عالم"
    expected_path = "ﺎﺒﺣﺮﻣ /usr/local/bin ﻢﻟﺎﻋ"
    assert arabic_rtl.process_text(inp_path) == expected_path
    assert arabic_rtl_cli.py_process_text(inp_path) == expected_path


def test_no_smart_mode():
    inp = "مرحبا `code`"
    result_cython = arabic_rtl.process_text(inp, smart_mode=False)
    result_python = arabic_rtl_cli.py_process_text(inp, smart_mode=False)
    assert result_cython == result_python
    assert "`" in result_cython
    assert result_cython.startswith("ﺎﺒﺣﺮﻣ")


def test_parallel_processing():
    text = ("السلام عليكم\n" * 150)
    res_single = arabic_rtl.process_text(text)
    res_parallel = arabic_rtl.process_text_parallel(text, num_threads=4)
    assert res_single == res_parallel

    res_py_parallel = arabic_rtl_cli.py_process_text_parallel(text, num_threads=4)
    assert res_single == res_py_parallel


def test_file_processing():
    text = "السلام عليكم ورحمة الله\n" * 50
    with tempfile.NamedTemporaryFile('w+', encoding='utf-8', delete=False) as f:
        f.write(text)
        f_path = f.name

    out_file = f_path + ".out"
    out_file_py = f_path + ".py.out"

    try:
        arabic_rtl.process_file_parallel(f_path, num_threads=2, output=out_file)
        with open(out_file, 'r', encoding='utf-8') as f_out:
            content = f_out.read()
        assert content == "ﷲ ﺔﻤﺣﺭﻭ ﻢﻜﻴﻠﻋ ﻡﻼﺴﻟﺍ\n" * 50

        # Also test Python fallback file processing mmap
        arabic_rtl_cli.py_process_file_mmap(f_path, num_threads=2, output=out_file_py)
        with open(out_file_py, 'r', encoding='utf-8') as f_out:
            content_py = f_out.read()
        assert content_py == "ﷲ ﺔﻤﺣﺭﻭ ﻢﻜﻴﻠﻋ ﻡﻼﺴﻟﺍ\n" * 50
    finally:
        if os.path.exists(f_path):
            os.remove(f_path)
        if os.path.exists(out_file):
            os.remove(out_file)
        if os.path.exists(out_file_py):
            os.remove(out_file_py)


def test_cli_positional_arg():
    cmd = [sys.executable, "arabic_rtl_cli.py", "مرحبا بالعالم"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "ﻢﻟﺎﻌﻟﺎﺑ ﺎﺒﺣﺮﻣ" in res.stdout


def test_cli_stdin():
    cmd = [sys.executable, "arabic_rtl_cli.py"]
    res = subprocess.run(cmd, input="السلام عليكم", capture_output=True, text=True, check=True)
    assert "ﻢﻜﻴﻠﻋ ﻡﻼﺴﻟﺍ" in res.stdout


def test_cli_no_smart_flag():
    cmd = [sys.executable, "arabic_rtl_cli.py", "--no-smart", "مرحبا /path"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert res.stdout.strip() != ""


def test_cli_show_stats():
    cmd = [sys.executable, "arabic_rtl_cli.py", "--show-stats", "السلام عليكم"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "ﻢﻜﻴﻠﻋ ﻡﻼﺴﻟﺍ" in res.stdout
    assert "---" in res.stderr
    assert "proc(s)" in res.stderr or "lines/sec" in res.stderr


def test_cli_benchmark():
    cmd = [sys.executable, "arabic_rtl_cli.py", "--benchmark"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "Arabic RTL Benchmark" in res.stdout
    assert "ALL PASS" in res.stdout


def test_cli_file_options():
    text = "بسم الله الرحمن الرحيم\n"
    with tempfile.NamedTemporaryFile('w+', encoding='utf-8', delete=False) as f_in:
        f_in.write(text)
        in_path = f_in.name
    out_path = in_path + ".out"

    try:
        cmd = [sys.executable, "arabic_rtl_cli.py", "--file", in_path, "--output", out_path]
        subprocess.run(cmd, check=True)
        with open(out_path, 'r', encoding='utf-8') as f_out:
            out_text = f_out.read()
        assert out_text == "ﻢﻴﺣﺮﻟﺍ ﻦﻤﺣﺮﻟﺍ ﷲ ﻢﺴﺑ\n"
    finally:
        if os.path.exists(in_path):
            os.remove(in_path)
        if os.path.exists(out_path):
            os.remove(out_path)


def test_daemon_mode_lifecycle():
    # Make sure daemon is stopped initially
    subprocess.run([sys.executable, "arabic_rtl_daemon.py", "stop"], capture_output=True)

    try:
        # Start daemon via subprocess
        start_res = subprocess.run([sys.executable, "arabic_rtl_daemon.py", "start"], capture_output=True, text=True, check=True)
        assert "Daemon started" in start_res.stdout or "Daemon already running" in start_res.stdout

        # Check status
        status_res = subprocess.run([sys.executable, "arabic_rtl_daemon.py", "status"], capture_output=True, text=True, check=True)
        assert "Daemon running" in status_res.stdout

        # Test CLI daemon mode flag
        cmd = [sys.executable, "arabic_rtl_cli.py", "--daemon", "السلام عليكم"]
        cli_res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        assert cli_res.stdout.strip() == "ﻢﻜﻴﻠﻋ ﻡﻼﺴﻟﺍ"
    finally:
        # Stop daemon
        stop_res = subprocess.run([sys.executable, "arabic_rtl_daemon.py", "stop"], capture_output=True, text=True, check=True)
        assert "Daemon stopped" in stop_res.stdout or "not running" in stop_res.stdout


def test_cli_no_args_help():
    # Verify CLI prints usage help when executed with --help
    cmd = [sys.executable, "arabic_rtl_cli.py", "--help"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    assert "usage:" in res.stdout or "usage:" in res.stderr


def test_tashkeel_reversal():
    inp = "مَرْحَبًا"
    expected = "ﺎﺒًﺣَﺮْﻣَ"
    assert arabic_rtl.process_text(inp, strip_tashkeel=False, allah_ligature=False) == expected
    assert arabic_rtl_cli.py_process_text(inp, strip_tashkeel=False, allah_ligature=False) == expected


def test_numbers_preservation():
    # Test ASCII digits, Arabic-Indic digits ٠-٩, and mixed
    inp_ascii = "عام 2026"
    expected_ascii = "2026 ﻡﺎﻋ"
    assert arabic_rtl.process_text(inp_ascii) == expected_ascii
    assert arabic_rtl_cli.py_process_text(inp_ascii) == expected_ascii

    inp_arabic_digits = "عام٢٠٢٦"
    expected_arabic_digits = "٢٠٢٦ﻡﺎﻋ"
    assert arabic_rtl.process_text(inp_arabic_digits) == expected_arabic_digits
    assert arabic_rtl_cli.py_process_text(inp_arabic_digits) == expected_arabic_digits


def test_ansi_escape_sequences():
    inp = "\x1b[31mالسلام عليكم\x1b[0m"
    expected = "\x1b[31mﻢﻜﻴﻠﻋ ﻡﻼﺴﻟﺍ\x1b[0m"
    assert arabic_rtl.process_text(inp) == expected
    assert arabic_rtl_cli.py_process_text(inp) == expected

    # Test non-letter ANSI terminators like ~ or ?
    inp_bracket = "\x1b[200~السلام عليكم\x1b[201~"
    expected_bracket = "\x1b[200~ﻢﻜﻴﻠﻋ ﻡﻼﺴﻟﺍ\x1b[201~"
    assert arabic_rtl.process_text(inp_bracket) == expected_bracket
    assert arabic_rtl_cli.py_process_text(inp_bracket) == expected_bracket


def test_bracket_mirroring():
    inp = "مرحبا (123) بك"
    expected = "ﻚﺑ (123) ﺎﺒﺣﺮﻣ"
    assert arabic_rtl.process_text(inp) == expected
    assert arabic_rtl_cli.py_process_text(inp) == expected

    inp_brackets = "اختبار [عالم] {1}"
    expected_brackets = "{1} [ﻢﻟﺎﻋ] ﺭﺎﺒﺘﺧﺍ"
    assert arabic_rtl.process_text(inp_brackets) == expected_brackets
    assert arabic_rtl_cli.py_process_text(inp_brackets) == expected_brackets


def test_windows_paths_skipping():
    inp = "انظر C:\\Users\\test هنا"
    res_cython = arabic_rtl.process_text(inp)
    res_python = arabic_rtl_cli.py_process_text(inp)
    assert "C:\\Users\\test" in res_cython
    assert "C:\\Users\\test" in res_python


def test_quranic_and_smart_brackets():
    inp = "﴿قُلْ هُوَ اللَّهُ أَحَدٌ﴾"
    expected = "﴿ﺪٌﺣَﺃَ ﻪُﻠَّﻟﺍ ﻮَﻫُ ﻞْﻗُ﴾"
    assert arabic_rtl.process_text(inp, strip_tashkeel=False, allah_ligature=False) == expected
    assert arabic_rtl_cli.py_process_text(inp, strip_tashkeel=False, allah_ligature=False) == expected

    inp_quotes = "قال “السلام عليكم”"
    expected_quotes = "“ﻢﻜﻴﻠﻋ ﻡﻼﺴﻟﺍ” ﻝﺎﻗ"
    assert arabic_rtl.process_text(inp_quotes) == expected_quotes
    assert arabic_rtl_cli.py_process_text(inp_quotes) == expected_quotes


def test_multiline_code_blocks():
    inp = "مرحبا\n```python\nprint('السلام عليكم')\n```\nعالم"
    res_cython = arabic_rtl.process_text(inp)
    res_python = arabic_rtl_cli.py_process_text(inp)
    assert res_cython == res_python
    assert "print('السلام عليكم')" in res_cython
    assert "ﺎﺒﺣﺮﻣ" in res_cython
    assert "ﻢﻟﺎﻋ" in res_cython


def test_file_and_mailto_urls():
    inp = "انظر file:///path/to/doc.txt أو mailto:test@example.com هنا"
    res_cython = arabic_rtl.process_text(inp)
    res_python = arabic_rtl_cli.py_process_text(inp)
    assert "file:///path/to/doc.txt" in res_cython
    assert "mailto:test@example.com" in res_cython
    assert "file:///path/to/doc.txt" in res_python
    assert "mailto:test@example.com" in res_python


def test_markdown_heading():
    inp = "# عنوان المقال"
    expected = "# ﻝﺎﻘﻤﻟﺍ ﻥﺍﻮﻨﻋ"
    assert arabic_rtl.process_text(inp) == expected
    assert arabic_rtl_cli.py_process_text(inp) == expected


def test_three_byte_ansi_sequences():
    inp = "\x1b(Bالسلام عليكم\x1b)0"
    expected = "\x1b(Bﻢﻜﻴﻠﻋ ﻡﻼﺴﻟﺍ\x1b)0"
    assert arabic_rtl.process_text(inp) == expected
    assert arabic_rtl_cli.py_process_text(inp) == expected


def test_env_variable_paths():
    inp = "انظر $HOME/test.txt هنا"
    res_cython = arabic_rtl.process_text(inp)
    res_python = arabic_rtl_cli.py_process_text(inp)
    assert "$HOME/test.txt" in res_cython
    assert "$HOME/test.txt" in res_python
    assert res_cython == res_python


def test_extended_brackets():
    inp = "اختبار 【عالم】 〔1〕"
    expected = "〔1〕 【ﻢﻟﺎﻋ】 ﺭﺎﺒﺘﺧﺍ"
    assert arabic_rtl.process_text(inp) == expected
    assert arabic_rtl_cli.py_process_text(inp) == expected


def test_honorific_diacritics():
    inp = "مُمَثَّلٌﷺ"
    res_cython = arabic_rtl.process_text(inp)
    res_python = arabic_rtl_cli.py_process_text(inp)
    assert res_cython == res_python


def test_extended_a_diacritics():
    inp = "كِتَابٌ\u08e3"  # Extended-A diacritic
    res_cython = arabic_rtl.process_text(inp)
    res_python = arabic_rtl_cli.py_process_text(inp)
    assert res_cython == res_python


def test_arabic_punctuation_reversal():
    inp = "مرحبا، عالم"
    expected = "ﻢﻟﺎﻋ ،ﺎﺒﺣﺮﻣ"
    assert arabic_rtl.process_text(inp) == expected
    assert arabic_rtl_cli.py_process_text(inp) == expected

    inp_q = "كيف حالك؟ بخير"
    expected_q = "ﺮﻴﺨﺑ ؟ﻚﻟﺎﺣ ﻒﻴﻛ"
    assert arabic_rtl.process_text(inp_q) == expected_q
    assert arabic_rtl_cli.py_process_text(inp_q) == expected_q


def test_parallel_code_block_preservation():
    # Construct text with multi-line code block across chunk boundaries
    code_block = "```python\ndef hello():\n    print('سلام')\n```\n"
    text = ("سطر عربي الأول\n" * 60) + code_block + ("سطر عربي ثاني\n" * 60)

    res_single = arabic_rtl.process_text(text)
    res_parallel = arabic_rtl.process_text_parallel(text, num_threads=4)
    assert res_single == res_parallel

    res_py_parallel = arabic_rtl_cli.py_process_text_parallel(text, num_threads=4)
    assert res_single == res_py_parallel
    assert "print('سلام')" in res_parallel


def test_cli_empty_piped_input():
    cmd = [sys.executable, "arabic_rtl_cli.py"]
    res = subprocess.run(cmd, input="", capture_output=True, text=True, check=True)
    assert res.stdout == ""
    assert res.stderr == ""


def test_daemon_stale_files_cleanup():
    # Simulate dead daemon by creating dummy PID/PORT files
    arabic_rtl_daemon.PID_FILE.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    arabic_rtl_daemon.PID_FILE.write_text("9999999")  # Non-existent PID
    arabic_rtl_daemon.PORT_FILE.write_text("55555")

    # is_running should report False and clean up dead files
    assert not arabic_rtl_daemon.is_running()
    assert not arabic_rtl_daemon.PID_FILE.exists()
    assert not arabic_rtl_daemon.PORT_FILE.exists()


def test_brackets_mirroring_and_nesting():
    cases = [
        ("(نص عربي)", "(ﻲﺑﺮﻋ ﺺﻧ)"),
        ("[نص عربي]", "[ﻲﺑﺮﻋ ﺺﻧ]"),
        ("«نص عربي»", "«ﻲﺑﺮﻋ ﺺﻧ»"),
        ("“نص عربي”", "“ﻲﺑﺮﻋ ﺺﻧ”"),
        ("‹نص عربي›", "‹ﻲﺑﺮﻋ ﺺﻧ›"),
        ("﴿نص عربي﴾", "﴿ﻲﺑﺮﻋ ﺺﻧ﴾"),
        ("（نص عربي）", "（ﻲﺑﺮﻋ ﺺﻧ）"),
    ]
    for inp, exp in cases:
        assert arabic_rtl.process_text(inp) == exp
        assert arabic_rtl_cli.py_process_text(inp) == exp


def test_numbers_floats_percentages_dates_times():
    cases = [
        ("النسبة هي 12.5% تقريبا", "ﺎﺒﻳﺮﻘﺗ 12.5% ﻲﻫ ﺔﺒﺴﻨﻟﺍ"),
        ("المبلغ 1,000 دينار", "ﺭﺎﻨﻳﺩ 1,000 ﻎﻠﺒﻤﻟﺍ"),
        ("التاريخ 2026/08/20", "2026/08/20 ﺦﻳﺭﺎﺘﻟﺍ"),
        ("التاريخ 2026-08-20", "2026-08-20 ﺦﻳﺭﺎﺘﻟﺍ"),
        ("الوقت 12:30", "12:30 ﺖﻗﻮﻟﺍ"),
        ("الوقت 12:30:45", "12:30:45 ﺖﻗﻮﻟﺍ"),
        ("درجة الحرارة +25 مئوية", "ﺔﻳﻮﺌﻣ +25 ﺓﺭﺍﺮﺤﻟﺍ ﺔﺟﺭﺩ"),
        ("الرصيد -50 دولار", "ﺭﻻﻭﺩ -50 ﺪﻴﺻﺮﻟﺍ"),
    ]
    for inp, exp in cases:
        assert arabic_rtl.process_text(inp) == exp
        assert arabic_rtl_cli.py_process_text(inp) == exp


def test_arabic_with_english_words_in_sentence():
    cases = [
        ("البرنامج مكتوب بلغة Python", "Python ﺔﻐﻠﺑ ﺏﻮﺘﻜﻣ ﺞﻣﺎﻧﺮﺒﻟﺍ"),
        ("هذا ملف README.md", "README.md ﻒﻠﻣ ﺍﺬﻫ"),
        ("اضغط على زر OK للمتابعة", "ﺔﻌﺑﺎﺘﻤﻠﻟ OK ﺭﺯ ﻰﻠﻋ ﻂﻐﺿﺍ"),
    ]
    for inp, exp in cases:
        assert arabic_rtl.process_text(inp) == exp
        assert arabic_rtl_cli.py_process_text(inp) == exp


def test_markdown_prefixes_and_headers():
    cases = [
        ("# عنوان رئيسي", "# ﻲﺴﻴﺋﺭ ﻥﺍﻮﻨﻋ"),
        ("## عنوان فرعي", "## ﻲﻋﺮﻓ ﻥﺍﻮﻨﻋ"),
        ("### قسم ثالث", "### ﺚﻟﺎﺛ ﻢﺴﻗ"),
        ("- [x] مهمة مكتملة", "- [x] ﺔﻠﻤﺘﻜﻣ ﺔﻤﻬﻣ"),
        ("- [ ] مهمة متبقية", "- [ ] ﺔﻴﻘﺒﺘﻣ ﺔﻤﻬﻣ"),
        ("> اقتباس مهم", "> ﻢﻬﻣ ﺱﺎﺒﺘﻗﺍ"),
        ("> [!NOTE] ملاحظة هامة", "> [!NOTE] ﺔﻣﺎﻫ ﺔﻈﺣﻼﻣ"),
        ("1. العنصر الأول", "1. ﻝﻭﻷﺍ ﺮﺼﻨﻌﻟﺍ"),
    ]
    for inp, exp in cases:
        assert arabic_rtl.process_text(inp) == exp
        assert arabic_rtl_cli.py_process_text(inp) == exp


def test_markdown_tables():
    inp = "| الاسم | العمر |\n| أحمد | 25 |"
    res_cython = arabic_rtl.process_text(inp)
    res_python = arabic_rtl_cli.py_process_text(inp)
    assert res_cython == res_python
    assert "ﻢﺳﻻﺍ" in res_cython
    assert "ﺪﻤﺣﺃ" in res_cython
    assert "25" in res_cython


def test_extended_unicode_diacritics_and_supplementary():
    # Extended-B diacritic
    inp_ext_b = "عَرَبِيّ\u0898"
    assert arabic_rtl.process_text(inp_ext_b) == arabic_rtl_cli.py_process_text(inp_ext_b)

    # Arabic mathematical supplementary
    inp_math = "رياضيات \U0001EE00"
    assert arabic_rtl.has_arabic(inp_math)
    assert arabic_rtl_cli.py_has_arabic(inp_math)


def test_cython_python_parity():
    test_suite = [
        "السلام عليكم ورحمة الله وبركاته",
        "المبلغ 5,250.75 $ فقط لا غير",
        "استخدم git clone https://github.com/test/repo.git للتحميل",
        "المسار هو /var/log/syslog على السيرفر",
        "(اختبار 1) مع [اختبار 2] و {اختبار 3}",
        "النسبة المئوية: 99.9%",
        "تاريخ اليوم 2026/08/20 والوقت 14:05:00",
    ]
    for text in test_suite:
        cy_res = arabic_rtl.process_text(text)
        py_res = arabic_rtl_cli.py_process_text(text)
        assert cy_res == py_res, f"Parity mismatch for: {text!r}\nCython: {cy_res!r}\nPython: {py_res!r}"


def test_cli_stream_mode():
    cmd = [sys.executable, "arabic_rtl_cli.py", "--stream"]
    inp = "مرحبا بالعالم\nسطر ثاني\n"
    res = subprocess.run(cmd, input=inp, capture_output=True, text=True, check=True)
    expected = "ﻢﻟﺎﻌﻟﺎﺑ ﺎﺒﺣﺮﻣ\nﻲﻧﺎﺛ ﺮﻄﺳ\n"
    assert res.stdout == expected


def test_decide_process_count_by_text_length():
    # Short text: should use 1 process (avoid multiprocessing overhead)
    short_text = "السلام عليكم ورحمة الله وبركاته\n" * 10
    assert arabic_rtl.decide_process_count(short_text) == 1
    assert arabic_rtl_cli.py_decide_process_count(short_text) == 1

    # Medium text: 200 lines -> 2 processes
    medium_text = "نص عربي لاختبار المعالجة المتعددة\n" * 200
    assert arabic_rtl.decide_process_count(medium_text, max_processes=8) == 2
    assert arabic_rtl_cli.py_decide_process_count(medium_text, max_processes=8) == 2

    # Moderate-large text: 1000 lines -> 4 processes
    mod_text = "سطر نص عربي للتأكد من توزيع المهام\n" * 1000
    assert arabic_rtl.decide_process_count(mod_text, max_processes=8) == 4
    assert arabic_rtl_cli.py_decide_process_count(mod_text, max_processes=8) == 4

    # Large text: 4000 lines -> 8 processes
    large_text = "معالجة نصوص عربية ضخمة بأعلى كفاءة\n" * 4000
    assert arabic_rtl.decide_process_count(large_text, max_processes=16) == 8
    assert arabic_rtl_cli.py_decide_process_count(large_text, max_processes=16) == 8

    # Very large text: 12000 lines -> 16 processes
    huge_text = "سطر ضخم جدا لتحديد أقصى عدد معالجات\n" * 12000
    assert arabic_rtl.decide_process_count(huge_text, max_processes=16) == 16
    assert arabic_rtl_cli.py_decide_process_count(huge_text, max_processes=16) == 16


def test_decide_process_count_constraints_and_types():
    large_text = "نص عربي طويل\n" * 5000

    # Max processes constraint
    assert arabic_rtl.decide_process_count(large_text, max_processes=2) == 2
    assert arabic_rtl.decide_process_count(large_text, max_processes=1) == 1
    assert arabic_rtl_cli.py_decide_process_count(large_text, max_processes=2) == 2
    assert arabic_rtl_cli.py_decide_process_count(large_text, max_processes=1) == 1

    # Passing list of lines
    lines_list = ["نص عربي"] * 300
    assert arabic_rtl.decide_process_count(lines_list, max_processes=8) == 2
    assert arabic_rtl_cli.py_decide_process_count(lines_list, max_processes=8) == 2

    # Passing line count as int
    assert arabic_rtl.decide_process_count(50, max_processes=8) == 1
    assert arabic_rtl.decide_process_count(300, max_processes=8) == 2
    assert arabic_rtl.decide_process_count(1500, max_processes=8) == 4
    assert arabic_rtl.decide_process_count(5000, max_processes=16) == 8
    assert arabic_rtl.decide_process_count(20000, max_processes=16) == 16

    # Parity check
    for count in [10, 80, 150, 400, 800, 2500, 8000, 20000]:
        assert arabic_rtl.decide_process_count(count) == arabic_rtl_cli.py_decide_process_count(count)


def test_auto_parallel_processing_execution():
    # Test auto process selection (num_threads=0) on short text
    short_text = "مرحبا بالعالم\n" * 10
    cy_short = arabic_rtl.process_text_parallel(short_text, num_threads=0)
    py_short = arabic_rtl_cli.py_process_text_parallel(short_text, num_threads=0)
    single_short = arabic_rtl.process_text(short_text)
    assert cy_short == single_short
    assert py_short == single_short

    # Test auto process selection on large text
    large_text = ("الحمد لله رب العالمين\n" * 150) + ("```python\nx = 1\n```\n") + ("الرحمن الرحيم\n" * 150)
    cy_large = arabic_rtl.process_text_parallel(large_text, num_threads=0)
    py_large = arabic_rtl_cli.py_process_text_parallel(large_text, num_threads=0)
    single_large = arabic_rtl.process_text(large_text)
    assert cy_large == single_large
    assert py_large == single_large








