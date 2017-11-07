#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import pytest

from selenium_docker.pool import (
    DriverPool, DriverPoolValueError, DriverPoolRuntimeException)


class BogusDriver:
    """ No-op object class. """


def test_pool_instantiation(factory):
    pool = DriverPool(5, factory=factory)
    assert pool.size == 5
    assert len(pool.name) == 6
    assert pool._drivers.qsize() == 0
    assert pool._drivers.maxsize == pool.size
    assert not pool.is_processing
    assert pool.proxy is None
    pool.quit()


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


@pytest.mark.current
def test_async_execution(factory):
    pool = DriverPool(1, factory=factory, use_proxy=False)
    pool.execute_async(lambda a, b: isinstance(b, int))

    pool.add_async(1, 2, 3, 4)
    pool.add_async([1, 2, 3, 4])

    assert all(list(pool.results(block=False)))

    pool.add_async(1, 2, 3, 4)
    pool.add_async([1, 2, 3, 4])

    assert all(list(pool.results(block=True)))
    assert len(list(pool.results(block=False))) == 0

    pool.quit()

    pool.execute_async(lambda a, b: isinstance(b, bool))
    pool.add_async(True, False)
    assert pool.stop_async() is None
    pool.quit()

