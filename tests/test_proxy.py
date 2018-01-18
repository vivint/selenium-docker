#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import pytest

from selenium_docker.proxy import AbstractProxy, SquidProxy


def test_abstract_proxy():
    proxy = AbstractProxy.make_proxy('none')
    assert proxy
    assert proxy.http_proxy == 'none'
    assert proxy.httpProxy == proxy.http_proxy
    proxy = AbstractProxy.make_proxy('localhost', 3128, 'https-localhost')
    assert proxy
    assert proxy.http_proxy == 'localhost:3128'
    assert proxy.ssl_proxy == 'https-localhost'


def test_proxy_container(factory):
    proxy = SquidProxy(factory=factory)
    assert proxy
    assert proxy.container
    assert 'squid3' in proxy.name
    assert 'running' == proxy.container.status
    proxy.quit()
