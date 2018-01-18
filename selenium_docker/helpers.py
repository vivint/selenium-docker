#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#   Copyright 2018 Vivint, inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
#    vivint-selenium-docker, 20017
# <<

import logging

from aenum import Flag
from toolz.functoolz import memoize
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as expect, ui

from selenium_docker.errors import SeleniumError

HTML_TAG = (By.TAG_NAME, 'html')
"""(str, str): tuple representing an <HTML> tag."""


class JsonFlags(Flag):
    """ :obj:`aenum.Flag` mixin to return members as JSON dict. """

    @classmethod
    def as_json(cls):
        """ Converts the Flag enumeration to a JSON structure.

        Returns:
            dict(str, int):
                Flag names and their corresponding integer-bit-value.
        """
        return {str(k): v.value for k, v in cls.__members__.items()}

    @classmethod
    def from_values(cls, *values):
        """ Creates a compound Flag instance.

        Logically OR's the integer/string ``values`` and returns a bit-flag
        that represents the features we want enabled in our Driver instance.

        Args:
            values (int or str): the integer-bit value or the flag name.

        Returns:
            :obj:`aenum.Flag`:
                Compound Flag instance with the features we requested.
        """
        ret = cls(0)
        for v in values:
            if isinstance(v, str):
                x = cls.__members__.get(v)
            elif isinstance(v, int):
                x = cls(v)
            elif v is None:
                continue
            else:
                raise ValueError(v)
            ret = ret | x
        return ret


class OperationsMixin(object):
    """ Optional mixin object to extend default driver functionality. """

    @property
    @memoize(key=lambda self: id(self))
    def _log(self):
        log = getattr(self, 'logger', None)
        if log and hasattr(log, 'exception'):
            return log
        else:
            logger = logging.getLogger('_blank')
            logger.addHandler(logging.NullHandler())
            return logger

    def switch_to_frame(self, selector, wait_for=HTML_TAG, max_time=30):
        """ Wait for a frame to load then switch to it.

        Note:
            Because there are two waits being performed in this operation
            the ``max_wait`` time could be doubled at most the value
            applied.

        Args:
            selector (tuple): ``iFrame`` we're looking for,
                in the form of ``(By, str)``.
            wait_for (tuple): element to wait for inside the iFrame,
                in the form of ``(By, str)``.
            max_time (int): time in seconds to wait for each element.

        Raises:
            Exception; when anything goes wrong.

        Returns:
            :obj:`~selenium.webdriver.remote.webelement.WebElement`:
                when there were no exceptions and the operation
                completed successfully.
        """
        wait = ui.WebDriverWait(self, max_time, poll_frequency=0.25)
        try:
            wait.until(expect.frame_to_be_available_and_switch_to_it(selector))
            wait.until(expect.visibility_of(wait_for))
            el = self.find_element(*wait_for)
        except SeleniumError as e:
            self._log.exception(e, exc_info=True)
            raise e
        return el
