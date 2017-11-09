#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

__author__ = 'Blake VandeMerwe'
__version__ = '0.4.1'
__license__ = 'MIT'
__contact__ = 'blake.vandemerwe@vivint.com'
__url__ = 'https://source.vivint.com/projects/DEVOPS/repos/vivint-selenium-docker'

import logging

from gevent.monkey import patch_socket

from selenium_docker.drivers.chrome import ChromeDriver, ChromeVideoDriver
from selenium_docker.drivers.firefox import FirefoxDriver, FirefoxVideoDriver
from selenium_docker.errors import SeleniumDockerException
from selenium_docker.helpers import JsonFlags
from selenium_docker.meta import config
from selenium_docker.pool import DriverPool
from selenium_docker.proxy import SquidProxy

__all__ = [
    'ChromeDriver',
    'ChromeVideoDriver',
    'DriverPool',
    'FirefoxDriver',
    'FirefoxVideoDriver',
    'JsonFlags',
    'SeleniumDockerException',
    'SquidProxy',
    'config'
]

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

patch_socket()
