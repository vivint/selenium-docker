#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import logging

from selenium.webdriver.support import ui
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as expect

from selenium_docker.utils import memoize

HTML_TAG = (By.TAG_NAME, 'html')
"""(str, str): tuple representing an <HTML> tag."""


class OperationsMixin(object):
    """ Optional mixin object to extend default driver functionality. """

    @property
    @memoize('ops_mixin_logger')
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
            :obj:`~selenium.webdriver.remote.webelement.WebElement`: when
                there were no exceptions and operation completed successfully.
        """
        wait = ui.WebDriverWait(self, max_time, poll_frequency=0.25)
        try:
            wait.until(expect.frame_to_be_available_and_switch_to_it(selector))
            wait.until(expect.visibility_of(wait_for))
            el = self.find_element(*wait_for)
        except Exception as e:
            self._log.exception(e, exc_info=True)
            raise e
        return el
