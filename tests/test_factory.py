#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import pytest
from docker.models.images import Image

from selenium_docker.base import (
    ContainerFactory, ContainerInterface, check_engine)


def test_container_interface():
    c = ContainerInterface()

    with pytest.raises(NotImplementedError):
        c.quit()

    with pytest.raises(NotImplementedError):
        c.close_container()

    with pytest.raises(NotImplementedError):
        c._make_container()

    assert c.CONTAINER is None
    c.CONTAINER = {}
    assert str(c) == '<ContainerInterface(image=None)>'


def test_container_factory():
    ContainerFactory.DEFAULT = None
    f = ContainerFactory(None, 'test_namespace')

    assert len(f.containers) == 0
    assert f.DEFAULT is f

    x = ContainerFactory(None, 'test_ns', make_default=False)
    assert x.DEFAULT is f

    assert f.namespace == 'test_namespace'
    s = str(f)
    assert s.startswith('<ContainerFactory(')
    assert 'count=0' in s
    assert 'ns=test_namespace' in s
    assert 'count' in f.as_json()
    assert f.as_json()['_ref'] == str(f) == s
    assert f.gen_name('vivint') == 'selenium-test_namespace-vivint'
    assert ContainerFactory.get_default_factory() is f


def test_get_containers():
    f = ContainerFactory(None, 'vivint')
    assert f.get_namespace_containers('vivint') == {}
    assert f.get_namespace_containers() == f.get_namespace_containers('vivint')

    c = f.start_container({
        'image': 'hello-world'
    }, detach=True)
    containers = f.get_namespace_containers()
    assert len(containers) == 1
    assert list(containers.keys())[0] == c.name
    assert c.ns == f.namespace
    assert isinstance(c.started, float)
    f.stop_all_containers()


def test_load_image():
    f = ContainerFactory(None, 'vivint')

    with pytest.raises(ValueError):
        f.load_image({})

    with pytest.raises(ValueError):
        f.load_image(None)

    img = f.load_image('hello-world', 'latest')
    assert isinstance(img, Image)
