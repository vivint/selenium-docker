#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import pytest

from selenium_docker.base import ContainerFactory


@pytest.fixture(scope='module')
def factory():
    f = ContainerFactory.get_default_factory('unittests')
    f.scrub_containers()
    yield f
    f.stop_all_containers()
