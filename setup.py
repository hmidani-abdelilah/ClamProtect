#!/usr/bin/env python3
from setuptools import setup, find_packages

setup(
    name="clamprotect",
    version="1.0.1",
    description="Modern ClamAV GUI — Real-time malware protection",
    author="ClamProtect Team",
    packages=find_packages(),
    py_modules=["main"],
    python_requires=">=3.10",
    install_requires=["PyQt5"],
    scripts=["resources/clamprotect-scan"],
    entry_points={
        "console_scripts": [
            "clamprotect=main:main",
        ],
    },
    data_files=[
        ("share/applications", ["resources/clamprotect.desktop"]),
        ("share/nautilus-python/extensions", ["resources/clamprotect_nautilus.py"]),
        ("share/kio/servicemenus", ["resources/clamprotect_dolphin.desktop"]),
    ],
)
