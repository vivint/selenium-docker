#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

from logging import getLogger

import gevent
from gevent.pool import Pool
from gevent.queue import Queue

from selenium_docker.base import ContainerFactory
from selenium_docker.drivers import ChromeDriver
from selenium_docker.proxy import SquidProxy
from selenium_docker.utils import gen_uuid


class DriverPool(object):
    def __init__(self, size, driver_cls=ChromeDriver, driver_cls_kw=None,
                 use_proxy=True, factory=None, name=None, logger=None):
        """ Create a pool of available Selenium containers for processing.

        Args:
            size (int): maximum concurrent tasks.
            driver_cls (:obj:`selenium.WebDriver`):
            driver_cls_kw (dict):
            use_proxy (bool):
            factory (:obj:`selenium_docker.base.ContainerFactory):
            name (str):
            logger (:obj:`logging.Logger`):
        """
        self.size = size
        self.name = name or gen_uuid(6)
        self.factory = factory or ContainerFactory.get_default_factory()
        self.logger = logger or getLogger('DriverPool.%s' % self.name)

        self._driver_cls = driver_cls
        self._driver_cls_kw = driver_cls_kw or {}
        self._drivers = Queue(maxsize=size)

        # post init inspections
        if not hasattr(self._driver_cls, 'CONTAINER'):
            raise ValueError('driver_cls must extend DockerDriver')

        # determine proxy usage
        if use_proxy:
            self.proxy = SquidProxy(factory=self.factory)
        else:
            self.proxy = None

        # deferred instantiation
        self._pool = None           # type: Pool
        self._results = None        # type: Queue
        self._tasks = None          # type: Queue
        self._processing = False    # type: bool

    @property
    def is_processing(self):
        """bool: whether or not we're currently processing tasks. """
        return self._processing

    def __bootstrap(self):
        if self._processing:
            # cannot run two executions simultaneously
            raise RuntimeError('cannot bootstrap pool, already running')
        self._processing = True
        self._results = Queue()
        self._tasks = Queue()
        self._load_drivers()

    def __cleanup(self, force=False):
        if self._processing and not force:
            raise RuntimeError('cannot cleanup driver pool while executing')
        # cleanup running drivers
        while not self._drivers.empty():
            d = self._drivers.get(block=True)
            d.quit()

    def _load_drivers(self):
        if not self._drivers.empty():
            return
        # we need to spin up our driver instances
        kw = dict(self._driver_cls_kw)
        kw.update({
            'proxy': self.proxy,
            'factory': self.factory,
        })

        def make_container(kw_args):
            d = self._driver_cls(**kw_args)
            self._drivers.put(d)

        threads = []
        for o in range(self.size):
            self.logger.debug('creating driver %d of %d', o + 1, self.size)
            threads.append(gevent.spawn(make_container, kw))
        for t in reversed(threads):
            t.join()
        if not self._drivers.full():
            raise RuntimeError('unable to fulfill required concurrent drivers')

    def close(self):
        self.__cleanup(force=True)

    def execute(self, fn, items, preserve_order=False, auto_clean=True,
                no_wait=False):
        """ Execute a fixed function, blocking for results. """

        def worker(o):
            """ Process work on item ``o``. """
            job_num, item = o
            self.logger.debug('doing work on item %d' % job_num)
            driver = self._drivers.get(block=True)
            ret_val = fn(driver, item)
            if not no_wait:
                gevent.sleep(3.0)
            self._drivers.put(driver)
            return ret_val

        self.__bootstrap()
        pool = Pool(size=self.size)
        if preserve_order:
            ittr = pool.imap
        else:
            ittr = pool.imap_unordered

        for o in ittr(worker, enumerate(items)):
            yield o

        self._processing = False
        if auto_clean:
            self.__cleanup()

    def execute_async(self, fn, *items):
        """ Execute a fixed function in the background, streaming results. """

        def worker(fn, task):
            driver = self._drivers.get(block=True)
            ret_val = fn(driver, task)
            gevent.sleep(1.0)
            self._results.put(ret_val)
            self._drivers.put(driver)

        def worker_cb(g):
            x = 1
            print('hi')

        def feeder():
            while True:
                while not self._tasks.empty():
                    task = self._tasks.get()
                    self._pool.apply_async(
                        worker,
                        args=(fn, task,),
                        callback=worker_cb)
                gevent.sleep(0.5)

        self.__bootstrap()
        if not self._pool:
            self._pool = Pool(size=self.size)
            gevent.spawn(feeder)
        for o in items:
            self._tasks.put(o)

    def results(self):
        pass



