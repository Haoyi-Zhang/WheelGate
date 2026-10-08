"""Offline-compatible packaging entry point; no research data in the software wheel."""
from pathlib import Path
from setuptools import setup
namespace = {}
exec((Path(__file__).parent/'wheelgate/__init__.py').read_text(), namespace)
setup(name='wheelgate', version=namespace['__version__'],
      description='Explicit consumer-operation qualification for local Python wheels',
      long_description=(Path(__file__).parent/'README.md').read_text(encoding='utf-8'),
      long_description_content_type='text/markdown', packages=['wheelgate'],
      python_requires='>=3.11', license='MIT',
      entry_points={'console_scripts':['wheelgate=wheelgate.runner:main']})
