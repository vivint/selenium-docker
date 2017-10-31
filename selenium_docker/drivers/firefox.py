#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

from aenum import auto
from selenium.webdriver import DesiredCapabilities, FirefoxProfile

from selenium_docker.drivers import DockerDriverBase, VideoDriver
from selenium_docker.helpers import JsonFlags


class Flags(JsonFlags):
    DISABLED    = 0
    X_IMG       = auto()
    X_FLASH     = auto()
    ALL         = ~DISABLED


class FirefoxDriver(DockerDriverBase):
    """ Firefox browser inside Docker.

    Inherits from :obj:`~selenium_docker.drivers.DockerDriverBase`.
    """

    BROWSER = 'Firefox'
    CONTAINER = dict(
        image='selenium/standalone-firefox',
        detach=True,
        labels={'role': 'browser',
                'dynamic': 'true',
                'browser': 'firefox',
                'hub': 'false'},
        mem_limit='480mb',
        ports={DockerDriverBase.SELENIUM_PORT: None},
        publish_all_ports=True)
    DEFAULT_ARGUMENTS = [
        ('browser.startup.homepage', 'about:blank')
    ]

    Flags = Flags

    def _capabilities(self, arguments, extensions, proxy, user_agent):
        """ Compile the capabilities of FirefoxDriver inside the Container.

        Args:
            arguments (list): unused.
            extensions (list): unused.
            proxy (Proxy): adds proxy instance to DesiredCapabilities.
            user_agent (str): unused.

        Returns:
            dict
        """
        self.logger.debug('building capabilities')
        c = DesiredCapabilities.FIREFOX.copy()
        if proxy:
            proxy.add_to_capabilities(c)
        return c

    def _profile(self, arguments, extensions, proxy, user_agent):
        """ Compile the capabilities of ChromeDriver inside the Container.

        Args:
            arguments (list):
            extensions (list):
            proxy (Proxy): unused.
            user_agent (str):

        Returns:
            FirefoxProfile
        """
        self.logger.debug('building browser profile')
        profile = FirefoxProfile()
        args = list(self.DEFAULT_ARGUMENTS)

        if self.f(Flags.X_IMG):
            args.append(
                ('permissions.default.image', '2'))

        if self.f(Flags.X_FLASH):
            args.append(
                ('dom.ipc.plugins.enabled.libflashplayer.so', 'false'))

        for ext in extensions:
            profile.add_extension(ext)

        args.extend(arguments)
        for arg_k, value in args:
            profile.set_preference(arg_k, value)
        if user_agent:
            profile.set_preference('general.useragent.override', user_agent)
        return profile


class FirefoxVideoDriver(VideoDriver, FirefoxDriver):
    """ Firefox browser inside Docker with video recording.

    Inherits from :obj:`~selenium_docker.drivers.VideoDriver`.
    """
    CONTAINER = dict(
        image='standalone-firefox-ffmpeg',
        detach=True,
        labels={'role': 'browser',
                'dynamic': 'true',
                'browser': 'firefox',
                'hub': 'false'},
        mem_limit='700mb',
        ports={DockerDriverBase.SELENIUM_PORT: None},
        publish_all_ports=True)
