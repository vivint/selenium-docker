#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import logging

from selenium.webdriver.common.proxy import Proxy, ProxyType

from selenium_docker.base import ContainerFactory, ContainerInterface
from selenium_docker.drivers import check_container
from selenium_docker.utils import gen_uuid, ip_port


class AbstractProxy(object):
    @staticmethod
    def make_proxy(http, port=None):
        # type: (str, int) -> Proxy
        """ Creates a Proxy instance to be used with Selenium drivers. """
        raise NotImplementedError('abstract method must be implemented')


class SquidProxy(ContainerInterface, AbstractProxy):
    SQUID_PORT = '3128/tcp'
    """str: identifier for extracting the host port that's bound to Docker."""

    CONTAINER = dict(
        image='minimum2scp/squid',
        detach=True,
        mem_limit='256mb',
        ports={SQUID_PORT: None},
        publish_all_ports=True,
        labels={'role': 'proxy',
                'dynamic': 'true'},
        restart_policy={
            'Name': 'on-failure'
        })
    """dict: default specification for the underlying container."""

    def __init__(self, logger=None, factory=None):
        self.name = 'squid3-' + gen_uuid()
        self.logger = logger or logging.getLogger(
            '%s.SquidProxy.%s' % (__name__, self.name))
        self.factory = factory or ContainerFactory.get_default_factory()
        self.factory.load_image(self.CONTAINER, background=False)
        self.container = self._make_container()
        conn, port = ip_port(self.container, self.SQUID_PORT)
        self.selenium_proxy = self.make_proxy(conn, port)

    @check_container
    def _make_container(self):
        """ Create a running container on the given Docker engine.

        Returns:
            :class:`~docker.models.containers.Container`
        """
        kwargs = dict(self.CONTAINER)
        kwargs.setdefault('name', self.name)
        self.logger.debug('creating container')
        c = self.factory.start_container(kwargs)
        c.reload()
        return c

    def close_container(self):
        """ Removes the running container from the connected engine via
        :obj:`.DockerDriverBase.factory`.

        Returns:
            None
        """
        self.factory.stop_container(name=self.name)

    @staticmethod
    def make_proxy(http, port=None, https=None, socks=None):
        """ Create a proxy the Selenium API can use.

        Args:
            http (str): URL for the HTTP proxy.
            port (int): HTTP proxy port.
            https (str): URL for the HTTPS proxy.
            socks (dict): with keys: ``url``, ``username`` and ``password``.

        Returns:
            :obj:`selenium.webdriver.common.proxy.Proxy`
        """
        if socks is None:
            socks = {}
        if port:
            http_url = '%s:%d' % (http, port)
        else:
            http_url = '%s' % http
        proxy = Proxy({
            'proxyType': ProxyType.MANUAL,
            'httpProxy': http_url,
            'sslProxy': https,
            'socksProxy': socks.get('url'),
            'socksUsername': socks.get('username'),
            'socksPassword': socks.get('password')
        })
        return proxy

    def quit(self):
        """ Alias for :func:`DockerDriverBase.close_container`.

        Returns:
            None
        """
        self.logger.debug('proxy quit')
        self.close_container()
