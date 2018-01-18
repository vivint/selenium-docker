#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<
import os
import shutil
from datetime import datetime

import pytest

from selenium_docker.pool import (
    DriverPool, DriverPoolValueError, DriverPoolRuntimeException)
from selenium_docker.drivers.chrome import ChromeVideoDriver
from selenium_docker.drivers.firefox import FirefoxVideoDriver
from selenium_docker.utils import gen_uuid

class BogusDriver:
    """ No-op object class. """


def get_title(driver, url):
    driver.get(url)
    assert driver.title
    return driver.title


def test_pool_instantiation(factory):
    pool = DriverPool(5, factory=factory)
    assert pool.size == 5
    assert len(pool.name) == 6
    assert pool._drivers.qsize() == 0
    assert pool._drivers.maxsize == pool.size
    assert not pool.is_processing
    assert pool.proxy is None
    pool.quit()


def test_pool_failures(factory):
    with pytest.raises(DriverPoolValueError):
        DriverPool(2, driver_cls_args=32, use_proxy=False, factory=factory)

    with pytest.raises(DriverPoolValueError):
        DriverPool(2, driver_cls_kw='nope', use_proxy=False, factory=factory)


def test_no_proxy(factory):
    pool = DriverPool(5, use_proxy=False, factory=factory)
    assert pool.proxy is None
    pool.close()


def test_bogus_drver_cls(factory):
    with pytest.raises(DriverPoolValueError):
        DriverPool(1, factory=factory, driver_cls=BogusDriver)


@pytest.mark.parametrize('proxy', [True, False])
def test_cleanup_browser(proxy, factory):
    def work(driver, item):
        assert item is True
        return item
    pool = DriverPool(3, use_proxy=proxy, factory=factory)
    assert pool._use_proxy is proxy
    results = [x for x in pool.execute(work,
                                       [True, True],
                                       preserve_order=proxy,
                                       auto_clean=False)]
    if proxy:
        assert pool.proxy.factory is pool.factory
    assert pool.is_processing
    pool.close()
    assert pool.proxy is None
    assert not pool.is_processing
    assert all(results)
    assert len(results) == 2
    assert pool._drivers.qsize() == 0
    pool.quit()
    assert len(pool.factory.containers) == 0
    assert pool.proxy is None


def test_async_failures(factory):
    pool = DriverPool(2, factory=factory, use_proxy=False)

    with pytest.raises(DriverPoolValueError):
        pool.execute_async(True)

    with pytest.raises(DriverPoolValueError):
        pool.execute_async(int, callback=True)

    with pytest.raises(DriverPoolRuntimeException):
        pool.execute_async(lambda s: s is True, items=[True, True])
        pool.execute_async(lambda s: s is True, items=[True, True])
    pool.stop_async()
    assert not pool.is_processing

    with pytest.raises(DriverPoolValueError):
        pool.execute_async(lambda s: s is True)
        pool.add_async()

    with pytest.raises(DriverPoolRuntimeException):
        pool.execute_async(lambda s: s is True)
        pool.execute(int, [])

    pool.quit()


def test_async_to_sync_failure(factory):
    pool = DriverPool(2, factory=factory, use_proxy=False)
    pool.execute_async(lambda a, b: b is True, [True])
    with pytest.raises(DriverPoolRuntimeException):
        pool.execute(lambda a, b: b is False, [False])


def test_async_execution(factory):
    pool = DriverPool(1, factory=factory, use_proxy=False)
    pool.execute_async(lambda a, b: isinstance(b, int))

    pool.add_async(1, 2, 3, 4)
    pool.add_async([1, 2, 3, 4])

    assert pool.is_async
    assert pool.is_processing
    assert all(list(pool.results(block=False)))

    pool.add_async(1, 2, 3, 4)
    pool.add_async([1, 2, 3, 4])

    assert all(list(pool.results(block=True)))
    assert len(list(pool.results(block=False))) == 0

    pool.stop_async()

    pool.execute_async(lambda a, b: isinstance(b, bool))
    pool.add_async(True, False)
    assert pool.stop_async() is None
    pool.quit()


@pytest.mark.parametrize('driver', [ChromeVideoDriver, FirefoxVideoDriver])
def test_pool_with_video_driver(driver, factory):
    now = datetime.now()
    urls = ['https://vivint.com', 'https://google.com']
    folder = os.path.join('/tmp', gen_uuid(8))
    os.makedirs(folder)

    pool = DriverPool(2, driver, (folder,), use_proxy=False,
                      factory=factory)
    for title in pool.execute(get_title, urls):
        assert title
    path = os.path.join(*map(str, [folder, now.year, now.month, now.day]))
    assert os.path.exists(path)
    assert os.path.isdir(path)
    shutil.rmtree(folder)


def test_pool_iter(factory):
    pool = DriverPool(2, factory=factory, use_proxy=False)

    def is_true(driver, item):
        return bool(item)

    assert all(list(pool.execute(is_true, [True, 1])))

    pool.execute(is_true, [True, 1])
    assert all(list(pool))


def test_pool_iter_async(factory):
    pool = DriverPool(2, factory=factory, use_proxy=False)

    def is_true(driver, item):
        return bool(item)

    def assert_true(value):
        assert value

    def assert_false(value):
        assert not value

    pool.execute_async(is_true, [True, 1], assert_true)

    assert pool.is_async
    assert 'async=True' in str(pool)
    assert all(list(pool))

    pool.stop_async()

    pool.execute_async(is_true, [False, 0, None], callback=assert_false)
    assert not any(list(pool.results(block=True)))


def test_pool_repr(factory):
    pool = DriverPool(2, factory=factory, use_proxy=False)
    s = str(pool)
    assert 'DriverPool' in s
    assert 'size=2' in s
    assert 'async=False' in s
