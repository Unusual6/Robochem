from setuptools import setup, find_packages

setup(
    name="lamas",
    version="1.0.0",
    author="Elia Savino",
    author_email="elia.savino@me.com",
    description="Learning algorithms for multivariate analysis",
    packages=find_packages(),
    install_requires=[
        "numpy",
        "pandas",
        "scikit-learn",
        "scipy",
        "nmrglue",
        "matplotlib",
        "pywavelets",
        "fastdtw",
        "openpyxl",
        "colorama",
    ],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.9",
)
