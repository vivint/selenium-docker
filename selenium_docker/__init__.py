#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import string
import random
import logging
from functools import partial, wraps

import gevent
import docker
import requests
from dotmap import DotMap
from docker import DockerClient
from docker.models.containers import Container
from docker.models.images import Image
from docker.errors import DockerException
from tenacity import retry, wait_fixed, stop_after_delay
from toolz.functoolz import juxt
from selenium.webdriver.common.proxy import Proxy, ProxyType
from selenium.webdriver import (
    Remote, ChromeOptions, FirefoxProfile, DesiredCapabilities)

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

__references = {}
__all__ = [
    'DockerDriver', 'ChromeDocker', 'FirefoxDocker', 'SquidProxy',
    'DockerException', 'references'
]


def gen_uuid(length=4):
    """ Generate a random ID.

        Args:
            length (int): length of generated ID.

        Returns:
            str
    """
    return ''.join([random.choice(string.hexdigits) for _ in range(length)])


def ip_port(container, port):
    """ Returns an updated HostIp and HostPort from the container's
        network properties. Calls container reload on-call.

        Args:
            container (Container):
            port (str):
    """
    # make sure it's running, get the newest values
    port = str(port)
    container.reload()
    attr = DotMap(container.attrs)
    conn = attr.NetworkSettings.Ports[port][0]
    return conn.HostIp, int(conn.HostPort)


def make_proxy(http, port=None):
    """ Creates a Proxy instance to be used with Selenium drivers.

        Args:
            http (str):
            port (int):

        Returns:
            Proxy
    """
    proxy = Proxy()
    proxy.proxy_type = ProxyType.MANUAL
    proxy.http_proxy = '%s:%d' % (http, port)
    return proxy


def ref_counter(key, direction):
    """ Count the references for a given key. """
    def inner(fn):
        @wraps(fn)
        def wrap(*args, **kwargs):
            __references[inner.key] += inner.direction
            return fn(*args, **kwargs)
        return wrap
    __references.setdefault(key, 0)
    inner.key = key
    inner.direction = direction
    return inner


def references():
    return dict(__references.iteritems())


class DockerDriver(Remote):
    BASE_URL = 'http://{host}:{port}/wd/hub'
    BROWSER = 'Default'
    CONTAINER = None
    IDENTITY = 'DockerDriver'
    IMPLICIT_WAIT_SECONDS = 10.0
    QUIT_TIMEOUT_SECONDS = 3.0
    SELENIUM_PORT = '4444/tcp'

    def __init__(self, docker_engine=None, user_agent=None, proxy=None,
                 cargs=None, ckwargs=None, extensions=None, preload=False,
                 logger=None, name=None):
        """ Create a new generic Selenium Driver on a local or remote
            Docker engine.

            Args:
                docker_engine (DockerClient): connection to machine that will
                    be running the docker containers. The default is to use
                    the local machine configured from the environment.
                user_agent (str): overwrite browser's default user agent.
                proxy (Proxy,SquidProxy): Proxy (or SquidProxy) instance
                    that routes container traffic.
                cargs (list): container creation arguments.
                ckwargs (dict): container creation keyword arguments.
                extensions (list): list of file locations loaded as
                    browser extensions.
                preload (bool): download the docker image in advance. This can
                    help multiple containers load faster and also decrease
                    timeout exceptions. (default `False`)
                name (str): name of the container. It's recommend to leave the
                    value as `None` so container names can be generated on
                    demand as they're created.
        """
        args = cargs or []
        ckwargs = ckwargs or {}
        extensions = extensions or []

        # ensure we have a name defined for our container
        self._name = ckwargs.get('name', name) or 'selenium-%s' % gen_uuid()

        self.logger = logger or logging.getLogger(
            '%s.%s.%s' % (__name__, self.IDENTITY, self.name))

        # use a remote engine, or try to get one from the local environment.
        self._docker = docker_engine or docker.from_env()

        # grab the image before trying to issue a new container
        # .. this can improve reliability by reducing timeout errors
        if preload and self.CONTAINER and 'image' in self.CONTAINER:
            self.load_docker_image(self.CONTAINER['image'], background=False)

        # now we have a container in an external environment we need to track
        self.container, url = self._make_container(self._docker, **ckwargs)
        self._base_url = url

        # user_agent can also be a callable function to randomly select one
        #  at instantiation time
        user_agent = user_agent() if callable(user_agent) else user_agent

        # track our proxy instance
        self._proxy, self._proxy_container = None, None

        if isinstance(proxy, Proxy):
            # Selenium Proxy
            self._proxy_container = None
            self._proxy = proxy

        elif isinstance(proxy, SquidProxy):
            # Container for SquidProxy, extract Selenium portion
            self._proxy_container = proxy
            self._proxy = proxy.selenium_proxy

        elif proxy is not None:
            raise ValueError('invalid proxy type, %s' % type(proxy))

        fn = juxt(self._capabilities, self._profile)
        capabilities, profile = fn(args, extensions, self._proxy, user_agent)

        super(DockerDriver, self).__init__(
            url, desired_capabilities=capabilities, browser_profile=profile,
            keep_alive=True)

        # driver configuration
        self.implicitly_wait(self.IMPLICIT_WAIT_SECONDS)

    @property
    def name(self):
        # type: () -> str
        """ Read-only property of the container's name. """
        return self._name

    @property
    def base_url(self):
        # type: () -> str
        """ Read-only property of Selenium's base url. """
        return self._base_url

    def load_docker_image(self, image, tag=None, insecure_registry=False,
                          background=False):
        """ Issue a `docker pull` command before attempting to start/run
            containers. This could potentially alliviate startup time, as well
            as ensure the containers are up-to-date.

            Args:
                image (str):
                tag (str):
                insecure_registry (bool):
                background (bool):

            Returns:
                Image
        """
        if tag is None:
            tag = ''
        self.logger.debug('pre-loading docker image %s:%s', image, tag)
        fn = partial(self._docker.images.pull, image, tag=tag,
                     insecure_registry=insecure_registry)
        if background:
            gevent.spawn(fn)
        else:
            return fn()

    def quit(self):
        self.logger.debug('browser quit')
        self.close_container()

    @ref_counter('docker-container', -1)
    def close_container(self, and_proxy=False):
        self.logger.debug('closing and removing container')
        self.container.stop()
        self.container.remove()
        if references().get('docker-container', 0) <= 0 and and_proxy:
            if self._proxy and self._proxy_container:
                self.logger.debug('closing proxy container')
                self._proxy_container.close_container()
            elif self._proxy:
                self.logger.warning('dangling proxy container still running')

    def _capabilities(self, *args):
        # type: (*Any) -> dict
        return dict()

    def _profile(self, *args):
        # type: (*Any) -> Any
        return None

    @ref_counter('docker-container', +1)
    def _make_container(self, engine, **kwargs):
        """ Create a running container on the given Docker engine. This
            container will contain the Selenium runtime, and ideally a
            browser instance to connect with.

            Args:
                engine (DockerClient):
                **kwargs (dict):
        """
        # ensure we don't already have a container created for this instance
        if hasattr(self, 'container') and \
                getattr(self, 'container') is not None:
            raise DockerException(
                'container already exists for this driver instance (%s)' %
                self.container.name)

        if self.CONTAINER is None:
            raise DockerException('cannot create container with definition')

        self.logger.debug('creating container')

        kw = dict(self.CONTAINER)
        kw.update(kwargs)
        kw.setdefault('name', self.name)

        @retry(wait=wait_fixed(0.5), stop=stop_after_delay(10))
        def check_selenium_up(base_url):
            self.logger.debug('checking selenium status')
            resp = requests.get(base_url, timeout=(1.0, 1.0))
            # retry on every exception
            resp.raise_for_status()

        try:
            container = engine.containers.run(**kw)
            host, port = ip_port(container, self.SELENIUM_PORT)
            base_url = self.BASE_URL.format(host=host, port=port)
        except DockerException as e:
            self.logger.exception(e, exc_info=True)
            raise e
        else:
            self.logger.debug('waiting for selenium to initialize')
            check_selenium_up(base_url)

        self.logger.debug('container created successfully')
        return container, base_url


class ChromeDocker(DockerDriver):
    BROWSER = 'Chrome'
    CONTAINER = dict(
        image='selenium/standalone-chrome',
        detach=True,
        mem_limit='480mb',
        ports={DockerDriver.SELENIUM_PORT: None},
        publish_all_ports=True)
    DEFAULT_ARGUMENTS = [
        '--disable-translate',
        '--start-maximized'
    ]

    def _capabilities(self, arguments, extensions, proxy, user_agent):
        # type: (list, list, Proxy, str) -> dict
        options = ChromeOptions()
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

    def _profile(self, *args):
        # type: (*Any) -> None
        return None


class FirefoxDocker(DockerDriver):
    BROWSER = 'Firefox'
    CONTAINER = dict(
        image='selenium/standalone-firefox',
        detach=True,
        mem_limit='480mb',
        ports={DockerDriver.SELENIUM_PORT: None},
        publish_all_ports=True)
    DEFAULT_ARGUMENTS = [
        ('browser.startup.homepage', 'about:blank')
    ]

    def _capabilities(self, arguments, extensions, proxy, user_agent):
        # type: (list, list, Proxy, str) -> dict
        c = DesiredCapabilities.FIREFOX.copy()
        if proxy:
            proxy.add_to_capabilities(c)
        return c

    def _profile(self, arguments, extensions, proxy, user_agent):
        # type: (list, list, Proxy, str) -> FirefoxProfile
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


class SquidProxy(object):
    SQUID_PORT = '3128/tcp'
    CONTAINER = dict(
        image='minimum2scp/squid',
        detach=True,
        mem_limit='256mb',
        ports={SQUID_PORT: None},
        publish_all_ports=True,
        restart_policy={
            'Name': 'on-failure'
        })

    def __init__(self, docker_=None, logger=None):
        self.name = 'squid3-' + gen_uuid(4)
        self.logger = logger or logging.getLogger(
            '%s.SquidProxy.%s' % (__name__, self.name))
        docker_ = docker_ or docker.from_env()
        self.container = self._make_container(docker_)
        conn, port = ip_port(self.container, self.SQUID_PORT)
        self.selenium_proxy = make_proxy(conn, port)

    @ref_counter('squid-container', +1)
    def _make_container(self, docker_):
        # type: (DockerClient) -> Container
        kwargs = dict(self.CONTAINER)
        kwargs.setdefault('name', self.name)
        c = docker_.containers.run(**kwargs)
        c.reload()
        return c

    @ref_counter('squid-container', -1)
    def close_container(self):
        self.logger.debug('closing and removing container')
        self.container.stop()
        self.container.remove()
