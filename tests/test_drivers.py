#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import pytest

from selenium_docker.drivers import DockerDriverBase
from selenium_docker.drivers.chrome import ChromeDriver
from selenium_docker.drivers.firefox import FirefoxDriver


@pytest.mark.parametrize('cls', [ChromeDriver, FirefoxDriver])
@pytest.mark.parametrize('ua', [None, 'custom', lambda: 'custom-fn'])
def test_driver(cls, ua, factory):
    for attr in ['BROWSER', 'CONTAINER', 'DEFAULT_ARGUMENTS', 'SELENIUM_PORT',
                 'Flags']:
        assert hasattr(cls, attr)

    flags = cls.Flags

    for flag in [flags.ALL, flags.DISABLED]:
        driver = cls(user_agent=ua, flags=flag, factory=factory)
        assert isinstance(driver, DockerDriverBase)
        driver.get('https://vivint.com')
        assert driver.title
        driver.quit()
        driver.close_container()

