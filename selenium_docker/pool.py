#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

from logging import getLogger

import gevent
from gevent.pool import Pool
from gevent.queue import Queue, JoinableQueue
from toolz.itertoolz import count

from selenium_docker.base import ContainerFactory
from selenium_docker.drivers.chrome import ChromeDriver
from selenium_docker.proxy import SquidProxy
from selenium_docker.utils import gen_uuid


class DriverPool(object):
    
    INNER_THREAD_SLEEP = 0.5
    
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
        # type: ContainerFactory
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
        self._tasks = None          # type: JoinableQueue
        self._processing = False    # type: bool
        self.__feeder_green = None  # type: gevent.Greenlet

    @property
    def is_processing(self):
        """bool: whether or not we're currently processing tasks. """
        return self._processing

    def __bootstrap(self):
        if self._processing:
            # cannot run two executions simultaneously
            raise RuntimeError('cannot bootstrap pool, already running')
        if self._pool:
            self._pool.join(timeout=10.0)
            self._pool.kill()
            self._pool = None
        self.logger.debug('bootstrapping pool processing')
        self._processing = True
        self._results = Queue()
        self._tasks = JoinableQueue()
        self._load_drivers()

    def __cleanup(self, force=False):
        if self._processing and not force:
            raise RuntimeError('cannot cleanup driver pool while executing')
        squid = None    # type: gevent.Greenlet
        if self.proxy:
            self.logger.debug('closing squid proxy')
            squid = gevent.spawn(self.proxy.quit)
        self.logger.debug('closing all driver containers')
        while not self._drivers.empty():
            d = self._drivers.get(block=True)
            d.quit()
        if self.proxy:
            squid.join()

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
        """ Execute a fixed function, blocking for results.

        Args:
            fn (Callable): function that takes two parameters, ``driver`` and
                ``task``.
            items (list(Any)): list of items that need processing. Each item is
                applied one at a time to an available driver from the pool.
            preserve_order (bool): should the results be returned in the order
                they were supplied via ``items``. It's more performant to
                allow results to return in any order.
            auto_clean (bool): cleanup docker containers after executing. If
                multiple processing tasks are going to be used, it's more
                performant to leave the containers running and reuse them.
            no_wait (bool): forgo a small sleep interval between finishing
                a task and putting the driver back in the available drivers
                pool.

        Yields:
            results: the result for each item as they're finished.
        """

        def worker(o):
            job_num, item = o
            self.logger.debug('doing work on item %d' % job_num)
            driver = self._drivers.get(block=True)
            ret_val = fn(driver, item)
            if not no_wait:
                gevent.sleep(self.INNER_THREAD_SLEEP)
            self._drivers.put(driver)
            return ret_val

        self.__bootstrap()
        self.logger.debug('starting sync processing')
        pool = Pool(size=self.size + 3)  # headroom
        if preserve_order:
            ittr = pool.imap
        else:
            ittr = pool.imap_unordered

        self._pool = pool
        self.logger.debug('yielding processed results')
        for o in ittr(worker, enumerate(items)):
            yield o

        self.logger.debug('stopping sync processing')
        self._processing = False
        if auto_clean:
            self.__cleanup()

    def stop_async(self, timeout=None, auto_clean=True):
        """ Stop all the async worker processing from executing.

        Args:
            timeout (float): number of seconds to wait for pool to finish
                processing before killing and closing out the execution.
            auto_clean (bool): cleanup docker containers after executing. If
                multiple processing tasks are going to be used, it's more
                performant to leave the containers running and reuse them.
        Yields:
            results: one result at a time, all that have been finished up
                until this point.

        Raises:
            StopIteration: after all results have been yielded to the caller.
        """
        self.logger.debug('stopping async processing')
        self._processing = False
        self.logger.debug('killing async feeder thread')
        if self.__feeder_green:
            gevent.kill(self.__feeder_green)
            self.__feeder_green = None
        self.logger.debug('joining async pool before kill')
        if self._pool:
            self._pool.join(timeout=timeout or 1.0)
            self._pool.kill(block=True)
        if auto_clean:
            self.close()
        tasks_count = self._tasks.qsize()
        self.logger.info('%d tasks remained unprocessed', tasks_count)

    def execute_async(self, fn, items=None, callback=None):
        """ Execute a fixed function in the background, streaming results.

        Args:
            fn (Callable): function that takes two parameters, ``driver`` and
                ``task``.
            items (list(Any)): list of items that need processing. Each item is
                applied one at a time to an available driver from the pool.
            callback (Callable): function that takes a single parameter, the
                return value of ``fn`` when its finished processing and has
                returned the driver to the queue.

        Returns:
            None
        """

        def worker(fn, task):
            async_task_id = gen_uuid(12)
            self.logger.debug('starting async task %s', async_task_id)
            driver = self._drivers.get(block=True)
            ret_val = fn(driver, task)
            self._results.put(ret_val)
            self._drivers.put(driver)
            gevent.sleep(self.INNER_THREAD_SLEEP)
            return ret_val

        def worker_cb(task_result):
            self.logger.debug('finished async task')
            return True

        def feeder():
            self.logger.debug('starting async feeder thread')
            while True:
                while not self._tasks.empty():
                    task = self._tasks.get()
                    self._pool.apply_async(
                        worker,
                        args=(fn, task,),
                        callback=callback)
                gevent.sleep(self.INNER_THREAD_SLEEP)

        if callback is None:
            callback = worker_cb
        if not callable(callback):
            raise ValueError('cannot use %s, is not callable' % callback)

        self.logger.debug('starting async processing')
        self.__bootstrap()
        if not self._pool:
            self._pool = Pool(size=self.size)
        if not self.__feeder_green:
            self.__feeder_green = gevent.spawn(feeder)
        self.add_async(items)

    def add_async(self, items):
        """ Add additional items to the asynchronous processing queue.

        Args:
            items (list(Any)): list of items that need processing. Each item is
                applied one at a time to an available driver from the pool.

        Raises:
            StopIteration: when all items have been added.
        """
        if not items:
            raise ValueError(items)
        item_count = count(items)
        self.logger.debug('adding %d additional items to tasks', item_count)
        for o in items:
            self._tasks.put(o)

    def results(self, block=True):
        """ Iterate over available results from processed tasks.

        Args:
            block (bool): when ``True``, block this call until all tasks have
                been processed and all results have been returned. Otherwise
                this will continue indefinitely while tasks are dynamically
                added to the async processing queue.

        Yields:
            results: one result at a time as they're finished.

        Raises:
            StopIteration: when the processing is finished.
        """
        est_size = self._results.qsize()
        self.logger.debug('there are an estimated %d results', est_size)
        if block:
            self.logger.debug('blocking for results to finish processing')
            while (not self._tasks.empty() and not self._results.empty()) \
                    or self._processing:
                while not self._results.empty():
                    yield self._results.get()
                gevent.sleep(self.INNER_THREAD_SLEEP)
            raise StopIteration
        else:
            if est_size > 0:
                self.logger.debug('returning as many results as have finished')
            self._results.put(StopIteration)
            for result in self._results:
                yield result


