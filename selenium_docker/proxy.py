#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import logging

import docker
from docker import DockerClient
from docker.models.containers import Container
from selenium.webdriver.common.proxy import Proxy, ProxyType

from selenium_docker.utils import ip_port, gen_uuid, ref_counter


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
        restart_policy={
            'Name': 'on-failure'
        })

    def __init__(self, docker_=None, logger=None):
        self.name = 'squid3-' + gen_uuid()
        self.logger = logger or logging.getLogger(
            '%s.SquidProxy.%s' % (__name__, self.name))
        self._docker = docker_ or docker.from_env()
        self.container = self._make_container(docker_)
        conn, port = ip_port(self.container, self.SQUID_PORT)
        self.selenium_proxy = self.make_proxy(conn, port)

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

    @staticmethod
    def make_proxy(http, port=None):
        proxy = Proxy()
        proxy.proxy_type = ProxyType.MANUAL
        proxy.http_proxy = '%s:%d' % (http, port)
        return proxy
