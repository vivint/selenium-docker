#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import random

import pytest
import gevent
from docker.errors import ImageNotFound

from selenium_docker.base import ContainerFactory
from selenium_docker.utils import *


@pytest.mark.parametrize('i', range(100))
def test_gen_uuid(i):
    assert len(gen_uuid(i)) == i


@pytest.mark.parametrize('i', ['a', 1.0, None, -1.0, {}, []])
def test_gen_uuid_types(i):
    assert len(gen_uuid(i)) == 4


def test_gen_uuid_bools():
    assert len(gen_uuid(True)) == 1
    assert len(gen_uuid(False)) == 0


def test_in_container():
    assert not in_container()


def test_in_container_via_factory(factory):
    # type: (ContainerFactory) -> None
    output = factory.docker.containers.run(
        'standalone-chrome-ffmpeg', 'ls -la /')
    assert '.docker' in output


@pytest.mark.parametrize('port', [
    ('4444/tcp', None),
    ('4444/tcp', random.randint(30000, 35000))
])
def test_ip_port(port, factory):
    # type: (ContainerFactory) -> None
    port_str, port_int = port

    spec = {
        'image': 'standalone-chrome-ffmpeg',
        'labels': {'browser': 'chrome'},
        'detach': True,
        'ports': {port_str: port_int},
        'publish_all_ports': True
    }
    c = factory.start_container(spec)
    host, port = ip_port(c, port_str)
    assert host == '0.0.0.0'
    assert isinstance(port, int) and port > 10000
    factory.stop_all_containers()


@pytest.mark.parametrize('bg', [True, False])
def test_load_docker_image(bg, factory):
    # type: (ContainerFactory) -> None
    names = ['hello-world:latest', 'hello-world:linux']
    for img in names:
        try:
            factory.docker.images.remove(img, force=True, noprune=False)
        except ImageNotFound:
            pass
    images = factory.docker.images.list(name='hello-world')
    assert not images
    image = load_docker_image(factory.docker, 'hello-world', background=bg)
    if bg:
        gevent.wait([image], timeout=15.0)
        image = image.value
    assert 'hello-world:latest' in image.tags


@pytest.mark.parametrize('pack', [
    ({}, ''),
    ({'one': 1}, '-metadata one="1"'),
    ({'one': None}, ''),
    ({'two': True, 'three': False},
     '-metadata two="True" -metadata three="False"'),
    ({'one': '""'}, '')
])
def test_parse_metadata(pack):
    meta, expected = pack
    assert expected == parse_metadata(meta)
