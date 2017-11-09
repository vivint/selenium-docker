#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

from gevent.monkey import patch_all
patch_all()

import os

import pytest
import requests

from selenium_docker.drivers import DockerDriverBase
from selenium_docker.drivers.chrome import ChromeDriver, ChromeVideoDriver
from selenium_docker.drivers.firefox import FirefoxDriver, FirefoxVideoDriver
from selenium_docker.utils import gen_uuid


def download_file(url):
    local_filename = os.path.join('/tmp', gen_uuid(12))
    r = requests.get(url, stream=True)
    with open(local_filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=4096):
            if chunk:
                f.write(chunk)
    return local_filename


@pytest.mark.parametrize('cls', [
    ChromeDriver,
    ChromeVideoDriver,
    FirefoxDriver,
    FirefoxVideoDriver
])
@pytest.mark.parametrize('ua', [None, 'custom', lambda: 'custom-fn'])
def test_driver(cls, ua, factory):
    for attr in ['BROWSER', 'CONTAINER', 'DEFAULT_ARGUMENTS', 'SELENIUM_PORT',
                 'Flags']:
        assert hasattr(cls, attr)

    flags = cls.Flags

    for flag in [flags.ALL, flags.DISABLED]:
        driver = cls(user_agent=ua, flags=flag, factory=factory)
        print(driver)
        assert isinstance(driver, DockerDriverBase)
        driver.get('https://vivint.com')
        assert driver.title
        driver.quit()
        driver.close_container()


@pytest.mark.parametrize('pack', [
    (ChromeDriver, 'https://clients2.google.com/service/update2/crx?response=redirect&prodversion=49.0&x=id%3Dcfhdojbkjhnklbpkdaibdccddilifddb%26installsource%3Dondemand%26uc')
    # (FirefoxDriver, 'https://addons.mozilla.org/firefox/downloads/file/764081/adblock_plus-3.0.1-an+fx.xpi')
])
@pytest.mark.current
def test_extensions(pack, factory):
    cls, url = pack
    path = download_file(url)
    driver = cls(extensions=[path], factory=factory)
    driver.get('https://vivint.com')
    driver.quit()
