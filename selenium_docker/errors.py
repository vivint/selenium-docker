#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

from docker.errors import DockerException


class SeleniumDockerException(Exception):
    """ A base class from which all other exceptions inherit.

    If you want to catch all errors that might raise,
    catch this base exception.
    """


class DockerError(DockerException, SeleniumDockerException):
    pass


class SeleniumError(SeleniumDockerException):
    pass
