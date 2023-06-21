# -*- coding: utf-8 -*-
from setuptools import find_packages
from distutils.core import setup


with open('README.md') as file:
    long_desc = file.read()

__version__ = "7.9.7"

setup(
    name='quick_trade',
    author="Vlad Kochetov",
    author_email='vladyslavdrrragonkoch@gmail.com',
    packages=find_packages(),
    version=__version__,
    description='Library for easy management and customization of algorithmic trading.',
    long_description=long_desc,
    long_description_content_type="text/markdown",
    project_urls={
        'Documentation': 'https://quick-trade.github.io/quick_trade/#/',
        'Source': 'https://github.com/quick-trade/quick_trade',
        'Twitter': 'https://twitter.com/quick_trade_tw',
        'Bug Tracker': 'https://github.com/quick-trade/quick_trade/issues'
    },
    install_requires=[
        'numpy==1.24.3',
        'plotly==5.15.0',
        'pandas==2.0.2',
        'ta==0.10.2',
        'ccxt==3.1.47',
        'tqdm==4.65.0',
        'scikit-learn',
    ],
    download_url=f'https://github.com/quick-trade/quick_trade/archive/{__version__}.tar.gz',
    keywords=[
        'technical-analysis',
        'python3',
        'trading',
        'trading-bot',
        'trading',
        'binance-trading',
        'ccxt',
    ],
    license='cc-by-sa-4.0',
    classifiers=[
        'Intended Audience :: Financial and Insurance Industry',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3',
    ],
    python_requires='>=3.0',
)
