from setuptools import setup, Extension
import os
import sys

try:
    from Cython.Build import cythonize
    USE_CYTHON = True
except ImportError:
    USE_CYTHON = False

ext = ".pyx" if USE_CYTHON else ".c"

# Compiler-specific tuning
if sys.platform == 'win32':
    extra_compile = ['/O2', '/LTCG']
    extra_link = ['/LTCG']
else:
    extra_compile = ['-O3', '-ffast-math', '-flto', '-funroll-loops', '-fomit-frame-pointer', '-fno-exceptions']
    extra_link = ['-O3', '-flto']

if os.environ.get('ENABLE_NATIVE_TUNING') == '1':
    if sys.platform != 'win32':
        extra_compile.append('-march=native')
        extra_link.append('-march=native')

extensions = [
    Extension(
        "arabic_rtl",
        sources=[f"arabic_rtl{ext}"],
        extra_compile_args=extra_compile,
        extra_link_args=extra_link,
    )
]

if USE_CYTHON:
    ext_modules = cythonize(
        extensions,
        compiler_directives={
            'language_level': '3',
            'boundscheck': False,
            'wraparound': False,
            'cdivision': True,
            'initializedcheck': False,
            'nonecheck': False,
            'overflowcheck': False,
            'optimize.use_switch': True,
            'optimize.unpack_method_calls': True,
        },
    )
else:
    ext_modules = extensions

setup(
    name="arabic-rtl-processor",
    version="1.0.0",
    description="Blazing fast Arabic RTL text processor for LTR terminals",
    author="BaselCS",
    ext_modules=ext_modules,
    python_requires='>=3.10',
)

