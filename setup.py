#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#   vivint-selenium-docker, 2017
#
#       Additional selenium drivers that utilize docker containers for their UI
#
#   Blake VandeMerwe
#   blake.vandemerwe@vivint.com
# <<

import re
import sys
from os.path import dirname, join as pjoin
from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand

ATTRIBUTES = re.compile(r"^__(\w+)__\s+=\s+'(.*?)'$", re.S + re.M)

dname = dirname(__file__)

with open(pjoin(dname, 'selenium_docker', '__init__.py')) as ins_file:
    text = ins_file.read()
    attrs = ATTRIBUTES.findall(text)
    A = dict(attrs)

with open(pjoin(dname, 'requirements.txt')) as ins_file:
    requirements = map(str.strip, ins_file.readlines())


class RunTests(TestCommand):
    """
    Run the unit tests.
    By default, `python setup.py test` fails if tests/ isn't a Python
    module (that is, if the tests/ directory doesn't contain an
    __init__.py file). But the tests/ directory shouldn't contain an
    __init__.py file and tests/ shouldn't be a Python module. See
      http://doc.pytest.org/en/latest/goodpractices.html
    Running the unit tests manually here enables `python setup.py test`
    without tests/ being a Python module.
    """
    def run_tests(self):
        from unittest import TestLoader, TextTestRunner
        tests_dir = pjoin(dirname(__file__), 'tests')
        suite = TestLoader().discover(tests_dir)
        result = TextTestRunner().run(suite)
        sys.exit(0 if result.wasSuccessful() else -1)


long_description = (
    'Information and documentation found can be found'
    ' at %s' % A['url'])


setup(
    name='selenium-docker',
    version=A['version'],
    author=A['author'],
    author_email=A['contact'],
    url=A['url'],
    description='Additional selenium drivers that utilize docker containers for their UI.',
    long_description=long_description,
    packages=find_packages(),
    include_package_data=True,
    platforms=['any'],
    install_requires=list(requirements),
    extras_require={
        'dev': [
            'pytest',
            'sphinx',
            'sphinx-rtd-theme',
            'tox'
        ]
    },
    cmdclass={
        'test': RunTests
    },
    classifiers=[
        'Topic :: Software Development :: Libraries',
        'Natural Language :: English',
        'License :: OSI Approved :: MIT License',
        'Intended Audience :: Developers',
        'Development Status :: 4 - Beta',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7'
        'Programming Language :: Python :: 3.6'
    ]
)
