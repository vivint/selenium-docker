#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import time
import logging
from abc import abstractmethod
from functools import partial

import docker
import gevent
import requests
from six import string_types, add_metaclass
from toolz.functoolz import juxt
from docker.errors import DockerException
from docker.models.containers import Container
from selenium.webdriver import Remote
from selenium.webdriver.common.proxy import Proxy
from tenacity import retry, wait_fixed, stop_after_delay

from selenium_docker.utils import (
    ip_port, gen_uuid, load_docker_image, ref_counter)

_containers = []


class DockerDriverMeta(type):
    def __init__(cls, name, bases, dct):
        super(DockerDriverMeta, cls).__init__(name, bases, dct)


class ContainerFactory(object):
    def __init__(self, engine, namespace, logger=None):
        self._containers = {}
        self._engine = engine or docker.from_env()
        self._ns = namespace or gen_uuid(8)
        self.logger = logger or logging.getLogger(
            '%s.ContainerFactory.%s' % (__name__, self._ns))

    def __repr__(self):
        return '<ContainerFactory(docker=%s,ns=%s,count=%d)>' % (
            self._engine.api.base_url, self._ns, len(self._containers.keys()))

    @property
    def containers(self):
        return self._containers

    @property
    def docker(self):
        return self._engine

    @property
    def namespace(self):
        return self._ns

    def __bootstrap(self, container, **kwargs):
        # type: (Container, dict) -> Container
        """ Adds additional attributes and functions to Container instance. """
        c = container
        for k, v in kwargs.items():
            setattr(c, k, v)
        c.started = time.time()
        c.logger = logging.getLogger('%s.%s' % (__name__, kwargs.get('name')))
        c.ns = self._ns
        return c

    def _gen_name(self, key=None):
        # type: (str) -> str
        return 'council-%s-%s' % (self._ns, key or gen_uuid(6))

    def as_json(self):
        # type: () -> dict
        return {
            '_ref': str(self),
            'count': len(self.containers)
        }

    def load_image(self, image, tag=None, insecure_registry=False,
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
        fn = partial(self._engine.images.pull, image, tag=tag,
                     insecure_registry=insecure_registry)
        if background:
            gevent.spawn(fn)
        else:
            return fn()

    def start_container(self, spec, **kwargs):
        # type: (dict) -> Container
        if 'image' not in spec:
            raise DockerException('cannot create container without image')

        name = self._gen_name()

        kw = dict(spec)
        kw.update(kwargs)
        kw[name] = name

        try:
            container = self._engine.containers.run(**kw)
        except DockerException as e:
            self.logger.exception(e, exc_info=True)
            raise e

        # track this container
        self._containers[name] = self.__bootstrap(container, name=name)
        self.logger.debug('started container %s', name)
        return container

    def stop_container(self, name=None, key=None):
        # type: (str, str) -> None
        """ Remove an individual container by name or key."""
        if key and not name:
            name = self._gen_name(key=key)
        if not name:
            raise ValueError('`name` and `key` cannot both be None')
        if name not in self.containers:
            raise KeyError('container %s it not being tracked' % name)
        container = self.containers.pop(name)
        self.logger.debug('stopping container %s', name)
        container.stop()
        container.remove()

    def stop_all_containers(self):
        # type: () -> None
        """ Remove all containers from this namespace. """
        for name in self.containers.keys():
            self.stop_container(name=name)

    def scrub_containers(self):
        # type: () -> None
        """ Remove ALL containers that were dynamically created. """
        # attempt to stop all the containers normally
        self.stop_all_containers()
        # now close all dangling containers
        containers = self._engine.containers.list(
            filters={'label': 'browser'})
        self.logger.debug('found %d dangling containers', len(containers))
        for c in containers:
            c.stop()
            c.remove()


@add_metaclass(DockerDriverMeta)
class DockerDriver(Remote):
    BASE_URL = 'http://{host}:{port}/wd/hub'
    BROWSER = 'Default'
    CONTAINER = None
    IMPLICIT_WAIT_SECONDS = 10.0
    QUIT_TIMEOUT_SECONDS = 3.0
    SELENIUM_PORT = '4444/tcp'

    def __init__(self, docker_engine=None, user_agent=None, proxy=None,
                 cargs=None, ckwargs=None, extensions=None, preload=False,
                 logger=None, name=None, verify=True):
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
                verify (bool): perform a check to ensure Selenium is up and
                    running correctly.
        """
        args = cargs or []
        ckwargs = ckwargs or {}
        extensions = extensions or []

        # ensure we have a name defined for our container
        self._name = ckwargs.get('name', name) or 'selenium-%s' % gen_uuid()

        self.logger = logger or logging.getLogger(
            '%s.%s.%s' % (__name__, self.identity, self.name))

        # use a remote engine, or try to get one from the local environment.
        self._docker = docker_engine or docker.from_env()

        # grab the image before trying to issue a new container
        # .. this can improve reliability by reducing timeout errors
        if preload and self.CONTAINER and 'image' in self.CONTAINER:
            load_docker_image(self._docker,
                              self.CONTAINER['image'],
                              background=False)

        # now we have a container in an external environment we need to track
        self.container = self._make_container(self._docker, **ckwargs)
        self._base_url = self._get_url()

        if verify:
            self._perform_check_container_ready()

        # user_agent can also be a callable function to randomly select one
        #  at instantiation time
        user_agent = user_agent() if callable(user_agent) else user_agent

        # track our proxy instance
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

        fn = juxt(self._capabilities, self._profile)
        capabilities, profile = fn(args, extensions, self._proxy, user_agent)

        try:
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
    def name(self):
        # type: () -> str
        """ Read-only property of the container's name. """
        return self._name

    @property
    def identity(self):
        return self.__class__.__name__

    @property
    def base_url(self):
        # type: () -> str
        """ Read-only property of Selenium's base url. """
        return self._base_url

    @property
    def conn_container(self):
        return self.container

    def quit(self):
        self.logger.debug('browser quit')
        self.close_container()

    @ref_counter('docker-container', -1)
    def close_container(self):
        self.logger.debug('closing and removing container')
        _containers.remove(self.container)
        self.container.stop()
        self.container.remove()

    @abstractmethod
    def _capabilities(self, *args):
        assert args is not None
        return dict()

    @abstractmethod
    def _profile(self, *args):
        assert args is not None
        return None

    @abstractmethod
    @retry(wait=wait_fixed(0.5), stop=stop_after_delay(10))
    def check_container_ready(self):
        self.logger.debug('checking selenium status')
        resp = requests.get(self._base_url, timeout=(1.0, 1.0))
        # retry on every exception
        resp.raise_for_status()
        return resp.status_code == requests.codes.ok

    def _perform_check_container_ready(self):
        self.logger.debug('waiting for selenium to initialize')
        is_ready = self.check_container_ready()
        if not is_ready:
            raise DockerException('could not verify container was ready')
        self.logger.debug('container created successfully')
        return is_ready

    def _get_url(self):
        host, port = ip_port(self.conn_container, self.SELENIUM_PORT)
        base_url = self.BASE_URL.format(host=host, port=port)
        return base_url

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
            raise DockerException('cannot create container without definition')

        self.logger.debug('creating container')

        kw = dict(self.CONTAINER)
        kw.update(kwargs)
        kw.setdefault('name', self.name)

        try:
            container = engine.containers.run(**kw)
        except DockerException as e:
            self.logger.exception(e, exc_info=True)
            raise e

        # track this container
        _containers.append(container)
        return container