"""
Author: Elia Savino
github: github.com/EliaSavino

Happy Hacking!

Descr:

"""

from setuptools import setup, find_packages

setup(
    name="RoBrains",
    version="1.0.0",
    author="Elia Savino",
    author_email="elia.savino@me.com",
    description="Robochem machine learning and self optimisation suite",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    install_requires=[
        "numpy",
        "pandas",
        "scikit-learn",
        "scipy",
        "torch",
        "matplotlib",
        "botorch",
        "gpytorch",
        "colorama",
        "pyDOE",
        "streamlit",
        "fastapi",
        "uvicorn"
    ],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Robochem Team",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.10",
    extras_require={
        "dev": [
            "unittest",
            "black",
            "pre-commit",
        ]
    },
)
