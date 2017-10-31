#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import logging

from docker import DockerClient
from docker.models.containers import Container
from selenium.webdriver.common.proxy import Proxy, ProxyType

from selenium_docker.base import ContainerFactory
from selenium_docker.drivers import check_container
from selenium_docker.utils import ip_port, gen_uuid


class AbstractProxy(object):
    @staticmethod
    def make_proxy(http, port=None):
        # type: (str, int) -> Proxy
        """ Creates a Proxy instance to be used with Selenium drivers. """
        raise NotImplementedError('abstract method must be implemented')


class SquidProxy(AbstractProxy):
    SQUID_PORT = '3128/tcp'
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

    def __init__(self, logger=None, factory=None):
        self.name = 'squid3-' + gen_uuid()
        self.logger = logger or logging.getLogger(
            '%s.SquidProxy.%s' % (__name__, self.name))
        self.factory = factory or ContainerFactory.get_default_factory()
        self.factory.load_image(self.CONTAINER, background=False)
        self.container = self._make_container()
        conn, port = ip_port(self.container, self.SQUID_PORT)
        self.selenium_proxy = self.make_proxy(conn, port)

    def quit(self):
        """ Alias method for closing the container. """
        self.logger.debug('proxy quit')
        self.close_container()

    @check_container
    def _make_container(self):
        # type: (DockerClient) -> Container
        kwargs = dict(self.CONTAINER)
        kwargs.setdefault('name', self.name)
        self.logger.debug('creating container')
        c = self.factory.start_container(kwargs)
        c.reload()
        return c

    def close_container(self):
        self.factory.stop_container(name=self.name)

    @staticmethod
    def make_proxy(http, port=None, https=None, socks=None):
        if socks is None:
            socks = {}
        proxy = Proxy({
            'proxyType': ProxyType.MANUAL,
            'httpProxy': '%s:%d' % (http, port),
            'sslProxy': https,
            'socksProxy': socks.get('proxy'),
            'socksUsername': socks.get('username'),
            'socksPassword': socks.get('password')
        })
        return proxy
