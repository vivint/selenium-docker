#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import pytest

from selenium_docker.utils import *


@pytest.mark.parametrize('i', range(100))
def test_gen_uuid(i):
    assert len(gen_uuid(i)) == i


@pytest.mark.parametrize('i', ['a', 1.0, None, -1.0, {}, [], True])
def test_gen_uuid_types(i):
    assert len(gen_uuid(i)) == 4

