import pytest
import tempfile
import os

import arabic_rtl
import arabic_rtl_cli


def test_has_arabic():
    assert arabic_rtl.has_arabic("مرحبا") is True
    assert arabic_rtl.has_arabic("Hello World") is False
    assert arabic_rtl.has_arabic("Hello مرحبا World") is True
    assert arabic_rtl_cli.py_has_arabic("مرحبا") is True
    assert arabic_rtl_cli.py_has_arabic("Hello World") is False


def test_basic_reversal():
    inp = "الحمد لله"
    expected = "هلل دمحلا"
    assert arabic_rtl.process_text(inp) == expected
    assert arabic_rtl.reverse_arabic_text(inp) == expected
    assert arabic_rtl_cli.py_process_text(inp) == expected
    assert arabic_rtl_cli.reverse_arabic_text(inp) == expected


def test_spaces_preservation():
    # Test spaces between Arabic words and trailing spaces before non-Arabic text
    inp = "مرحبا      world"
    expected = "ابحرم      world"
    assert arabic_rtl.process_text(inp) == expected
    assert arabic_rtl_cli.py_process_text(inp) == expected

    inp2 = "  مرحبا  علي  "
    expected2 = "  يلع  ابحرم  "
    assert arabic_rtl.process_text(inp2) == expected2
    assert arabic_rtl_cli.py_process_text(inp2) == expected2


def test_smart_mode_skipping():
    # Code blocks
    inp = "مرحبا ```code``` عالم"
    expected = "ابحرم ```code``` ملاع"
    assert arabic_rtl.process_text(inp) == expected
    assert arabic_rtl_cli.py_process_text(inp) == expected

    # Inline code
    inp_inline = "مرحبا `var_name` عالم"
    expected_inline = "ابحرم `var_name` ملاع"
    assert arabic_rtl.process_text(inp_inline) == expected_inline
    assert arabic_rtl_cli.py_process_text(inp_inline) == expected_inline

    # URLs
    inp_url = "مرحبا https://example.com/test عالم"
    expected_url = "ابحرم https://example.com/test ملاع"
    assert arabic_rtl.process_text(inp_url) == expected_url
    assert arabic_rtl_cli.py_process_text(inp_url) == expected_url

    # Paths
    inp_path = "مرحبا /usr/local/bin عالم"
    expected_path = "ابحرم /usr/local/bin ملاع"
    assert arabic_rtl.process_text(inp_path) == expected_path
    assert arabic_rtl_cli.py_process_text(inp_path) == expected_path


def test_no_smart_mode():
    inp = "مرحبا `code`"
    # In no-smart mode, `code` non-Arabic characters are preserved but backticks are preserved as non-Arabic
    result_cython = arabic_rtl.process_text(inp, smart_mode=False)
    result_python = arabic_rtl_cli.py_process_text(inp, smart_mode=False)
    assert result_cython == result_python


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

    try:
        arabic_rtl.process_file_parallel(f_path, num_threads=2, output=out_file)
        with open(out_file, 'r', encoding='utf-8') as f_out:
            content = f_out.read()
        assert content == "هللا ةمحرو مكيلع مالسلا\n" * 50
    finally:
        if os.path.exists(f_path):
            os.remove(f_path)
        if os.path.exists(out_file):
            os.remove(out_file)
