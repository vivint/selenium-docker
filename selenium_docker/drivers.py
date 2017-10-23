#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import logging
from abc import abstractmethod
from functools import wraps

import requests
from six import add_metaclass
from toolz.functoolz import juxt
from docker.errors import DockerException, APIError
from tenacity import retry, wait_fixed, stop_after_delay
from selenium.webdriver.common.proxy import Proxy
from selenium.webdriver import Remote
from selenium.webdriver import (
    ChromeOptions, FirefoxProfile, DesiredCapabilities)

from selenium_docker.base import ContainerFactory
from selenium_docker.utils import ip_port, gen_uuid, ref_counter


def check_container(fn):
    """ Ensure we're not trying to double up an external container
        with a Python instance that already has one. This would create
        dangling containers that may not get stopped programmatically.
    """
    @wraps(fn)
    def inner(self, *args, **kwargs):
        # check the instance
        self.logger.debug('checking container before creation')
        if self.factory is None:
            raise DockerException('no docker client defined as factory')
        if getattr(self, 'container', None) is not None:
            raise DockerException(
                'container already exists for this driver instance (%s)' %
                self.container.name)
        # check the specification
        if self.CONTAINER is None:
            raise DockerException('cannot create container without definition')
        # check the docker connection
        try:
            self.factory.docker.ping()
        except APIError as e:
            self.logger.exception(e, exc_info=True)
            raise e
        else:
            self.logger.debug('checking passed')
            return fn(self, *args, **kwargs)
    return inner


class DockerDriverMeta(type):
    def __init__(cls, name, bases, dct):
        super(DockerDriverMeta, cls).__init__(name, bases, dct)


@add_metaclass(DockerDriverMeta)
class DockerDriver(Remote):
    BASE_URL = 'http://{host}:{port}/wd/hub'
    BROWSER = 'Default'
    CONTAINER = None
    IMPLICIT_WAIT_SECONDS = 10.0
    QUIT_TIMEOUT_SECONDS = 3.0
    SELENIUM_PORT = '4444/tcp'

    def __init__(self, user_agent=None, proxy=None, cargs=None, ckwargs=None,
                 extensions=None, logger=None, name=None, factory=None):
        """ Selenium compatible Remote Driver instance.

        Args:
            user_agent (str): overwrite browser's default user agent.
            proxy (Proxy,SquidProxy): Proxy (or SquidProxy) instance
                that routes container traffic.
            cargs (list): container creation arguments.
            ckwargs (dict): container creation keyword arguments.
            extensions (list): list of file locations loaded as
                browser extensions.
            logger (Logger): logging module Logger instance.
            name (str): name of the container. It's recommend to leave the
                value as `None` so container names can be generated on
                demand as they're created.
            factory (ContainerFactory):

        Raises:
            ValueError: when ``proxy`` is an unknown/invalid value.
            Exception: when any problem occurs connecting the driver to its
                underlying container.
        """
        args = cargs or []
        ckwargs = ckwargs or {}
        extensions = extensions or []

        # ensure we have a name defined for our container
        self._name = ckwargs.get('name', name) or 'selenium-%s' % gen_uuid()
        self.logger = logger or logging.getLogger(
            '%s.%s.%s' % (__name__, self.identity, self.name))

        ckwargs['name'] = self._name

        # create the container
        self.factory = factory or ContainerFactory.get_default_factory()
        self.factory.load_image(self.CONTAINER, background=False)
        self.container = self._make_container(**ckwargs)
        self._base_url = self._get_url()
        self._perform_check_container_ready()

        # user_agent can also be a callable function to randomly select one
        #  at instantiation time
        user_agent = user_agent() if callable(user_agent) else user_agent

        # figure out if we're using a proxy
        self._proxy, self._proxy_container = None, None
        if isinstance(proxy, Proxy):
            # Selenium Proxy
            self._proxy_container = None
            self._proxy = proxy
        elif hasattr(proxy, 'selenium_proxy'):
            # Container for SquidProxy, extract Selenium portion
            self._proxy_container = proxy
            self._proxy = proxy.selenium_proxy
        elif proxy is not None:
            raise ValueError('invalid proxy type, %s' % type(proxy))

        # build our web driver capabilities
        fn = juxt(self._capabilities, self._profile)
        capabilities, profile = fn(args, extensions, self._proxy, user_agent)
        try:
            # build our web driver
            super(DockerDriver, self).__init__(
                self._base_url, desired_capabilities=capabilities,
                browser_profile=profile, keep_alive=False)
        except Exception as e:
            self.logger.exception(e, exc_info=True)
            self.close_container()
            raise e

        # driver configuration
        self.implicitly_wait(self.IMPLICIT_WAIT_SECONDS)

    def __repr__(self):
        if not hasattr(self, 'session_id'):
            return '<%s(%s)>' % (self.identity, self._name)
        return super(DockerDriver, self).__repr__()

    @property
    def base_url(self):
        """str: read-only property of Selenium's base url. """
        return self._base_url

    @property
    def identity(self):
        """str: reference to the parent class' name. """
        return self.__class__.__name__

    @property
    def name(self):
        # type: () -> str
        """str: read-only property of the container's name. """
        return self._name

    def quit(self):
        """ Alias for :func:`.close_container`.

        Generally this is called in a Selenium test when you want to
        completely close and quit the active browser.

        Returns:
            None
        """
        self.logger.debug('browser quit')
        self.close_container()

    @ref_counter('docker-container', -1)
    def close_container(self):
        """ Removes the running container from the connected engine.

        Returns:
            None
        """
        self.logger.debug('closing and removing container')
        self.factory.stop_container(name=self.name)

    @abstractmethod
    def _capabilities(self, arguments, extensions, proxy, user_agent):
        raise NotImplementedError

    @abstractmethod
    def _profile(self, arguments, extensions, proxy, user_agent):
        raise NotImplementedError

    @retry(wait=wait_fixed(0.5), stop=stop_after_delay(10))
    def check_container_ready(self):
        """ Function that continuously checks if a container is ready.

        Note:
            This function should be wrapped in a `tenacity.retry` for
            continuously checking the status without failing.

        Returns:
            bool: ``True`` when the status is good. ``False`` if it cannot
                be verified or is in an unusable state.
        """
        self.logger.debug('checking selenium status')
        resp = requests.get(self._base_url, timeout=(1.0, 1.0))
        # retry on every exception
        resp.raise_for_status()
        return resp.status_code == requests.codes.ok

    def _perform_check_container_ready(self):
        """ Checks if the container is ready to use by calling seperate
        function.

        Raises:
            :exc:`~docker.errors.DockerException`: when the container's
                creation and state cannot be verified.

        Returns:
            bool
        """
        self.logger.debug('waiting for selenium to initialize')
        is_ready = self.check_container_ready()
        if not is_ready:
            raise DockerException('could not verify container was ready')
        self.logger.debug('container created successfully')
        return is_ready

    def _get_url(self):
        """ Extract the hostname and port from a running docker container,
        return it as a URL-string we can connect to.

        Returns:
            str
        """
        host, port = ip_port(self.container, self.SELENIUM_PORT)
        base_url = self.BASE_URL.format(host=host, port=port)
        return base_url

    @ref_counter('docker-container', +1)
    @check_container
    def _make_container(self, **kwargs):
        """ Create a running container on the given Docker engine.

        This container will contain the Selenium runtime, and ideally a
        browser instance to connect with.

        Args:
            **kwargs (dict): the specification of the docker container.

        Returns:
            :class:`~docker.models.containers.Container`
        """
        # ensure we don't already have a container created for this instance
        self.logger.debug('creating container')
        return self.factory.start_container(self.CONTAINER, **kwargs)


class ChromeDriver(DockerDriver):
    """ Chrome browser inside Docker. """

    BROWSER = 'Chrome'
    CONTAINER = dict(
        image='selenium/standalone-chrome',
        detach=True,
        labels={'browser': 'chrome', 'hub': 'true'},
        mem_limit='480mb',
        ports={DockerDriver.SELENIUM_PORT: None},
        publish_all_ports=True)
    DEFAULT_ARGUMENTS = [
        '--disable-translate',
        '--start-maximized'
    ]

    def _capabilities(self, arguments, extensions, proxy, user_agent):
        """ Compile the capabilities of ChromeDriver inside the Container.

        Args:
            arguments (list):
            extensions (list):
            proxy (Proxy):
            user_agent (str):

        Returns:
            ChromeOptions
        """
        options = ChromeOptions()
        options.add_experimental_option(
            'prefs', {'profile.managed_default_content_settings.images': 2})
        args = list(self.DEFAULT_ARGUMENTS)
        args.extend(arguments)
        for arg in args:
            options.add_argument(arg)
        if user_agent:
            options.add_argument('--user-agent=' + user_agent)
        for ext in extensions:
            options.add_extension(ext)
        c = options.to_capabilities()
        if proxy:
            proxy.add_to_capabilities(c)
        return c

    def _profile(self, arguments, extensions, proxy, user_agent):
        """ No-op for ChromeDriver. """
        return None


class FirefoxDriver(DockerDriver):
    """ Firefox browser inside Docker. """

    BROWSER = 'Firefox'
    CONTAINER = dict(
        image='selenium/standalone-firefox',
        detach=True,
        labels={'browser': 'firefox', 'hub': 'true'},
        mem_limit='480mb',
        ports={DockerDriver.SELENIUM_PORT: None},
        publish_all_ports=True)
    DEFAULT_ARGUMENTS = [
        ('browser.startup.homepage', 'about:blank')
    ]

    def _capabilities(self, arguments, extensions, proxy, user_agent):
        """ Compile the capabilities of FirefoxDriver inside the Container.

        Args:
            arguments (list): unused.
            extensions (list): unused.
            proxy (Proxy): adds proxy instance to DesiredCapabilities.
            user_agent (str): unused.

        Returns:
            dict
        """
        c = DesiredCapabilities.FIREFOX.copy()
        if proxy:
            proxy.add_to_capabilities(c)
        return c

    def _profile(self, arguments, extensions, proxy, user_agent):
        """ Compile the capabilities of ChromeDriver inside the Container.

        Args:
            arguments (list):
            extensions (list):
            proxy (Proxy): unused.
            user_agent (str):

        Returns:
            FirefoxProfile
        """
        profile = FirefoxProfile()
        for ext in extensions:
            profile.add_extension(ext)
        args = list(self.DEFAULT_ARGUMENTS)
        args.extend(arguments)
        for arg_k, value in args:
            profile.set_preference(arg_k, value)
        if user_agent:
            profile.set_preference('general.useragent.override', user_agent)
        return profile
