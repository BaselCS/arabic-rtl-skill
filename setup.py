from setuptools import setup, Extension
from Cython.Build import cythonize
import os

# Optimize for native CPU, maximum optimization
os.environ['CFLAGS'] = '-march=native -O3 -ffast-math -flto -funroll-loops'

extensions = [
    Extension(
        "arabic_rtl",
        sources=["arabic_rtl.pyx"],
        extra_compile_args=[
            '-march=native',
            '-O3',
            '-ffast-math',
            '-flto',
            '-funroll-loops',
            '-fomit-frame-pointer',
            '-fno-exceptions',
        ],
        extra_link_args=[
            '-march=native',
            '-O3',
            '-flto',
        ],
    )
]

setup(
    name="arabic_rtl_fast",
    version="1.0.0",
    description="Blazing fast Arabic RTL text processor for LTR terminals",
    author="basel",
    ext_modules=cythonize(
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
    ),
    python_requires='>=3.10',
)
