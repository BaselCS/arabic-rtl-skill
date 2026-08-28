from setuptools import setup, Extension
import os
import sys

try:
    from Cython.Build import cythonize
    USE_CYTHON = True
except ImportError:
    USE_CYTHON = False

ext = ".pyx" if USE_CYTHON else ".c"

# Compiler-specific tuning (1BRC extreme performance)
if sys.platform == 'win32':
    extra_compile = ['/O2', '/LTCG', '/openmp', '/arch:AVX2']
    extra_link = ['/LTCG', '/openmp']
else:
    extra_compile = [
        '-O3', '-march=native', '-ffast-math', '-flto',
        '-funroll-loops', '-fomit-frame-pointer', '-fno-exceptions',
        '-fopenmp'
    ]
    extra_link = ['-O3', '-flto', '-fopenmp']

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
    py_modules=["arabic_rtl_cli", "arabic_rtl_daemon"],
    entry_points={
        "console_scripts": [
            "arabic-rtl=arabic_rtl_cli:main",
            "arabic-rtl-daemon=arabic_rtl_daemon:main",
        ]
    },
    python_requires='>=3.10',
)

