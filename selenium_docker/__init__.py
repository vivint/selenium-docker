#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#   Copyright 2018 Vivint, inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
#    vivint-selenium-docker, 20017
# <<

__author__ = 'Blake VandeMerwe'
__version__ = '0.5.0'
__license__ = 'ALv2'
__contact__ = 'blake.vandemerwe@vivint.com'
__url__ = 'https://github.com/vivint/selenium-council'

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
