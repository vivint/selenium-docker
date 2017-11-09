#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

from aenum import auto
from selenium.webdriver.chrome.options import Options as ChromeOptions

from selenium_docker.drivers import DockerDriverBase, VideoDriver
from selenium_docker.helpers import JsonFlags

__all__ = [
    'Flags',
    'ChromeDriver',
    'ChromeVideoDriver'
]


class Flags(JsonFlags):
    DISABLED    = 0
    X_IMG       = auto()
    X_3D        = auto()
    X_OFFERS    = auto()
    ALL         = ~DISABLED


class ChromeDriver(DockerDriverBase):
    """ Chrome browser inside Docker.

    Inherits from :obj:`~selenium_docker.drivers.DockerDriverBase`.
    """

    BROWSER = 'Chrome'
    CONTAINER = dict(
        image='selenium/standalone-chrome',
        detach=True,
        labels={'role': 'browser',
                'dynamic': 'true',
                'browser': 'chrome',
                'hub': 'false'},
        mem_limit='480mb',
        ports={DockerDriverBase.SELENIUM_PORT: None},
        publish_all_ports=True)
    DEFAULT_ARGUMENTS = [
        '--data-reduction-proxy-lo-fi',
        '--disable-win32k-renderer-lockdown',
        '--start-maximized'
    ]

    Flags = Flags

    def _capabilities(self, arguments, extensions, proxy, user_agent):
        """ Compile the capabilities of ChromeDriver inside the Container.

        Args:
            arguments (list):
            extensions (list):
            proxy (Proxy):
            user_agent (str):

        Returns:
            dict
        """
        self.logger.debug('building capabilities')
        options = ChromeOptions()
        args = list(self.DEFAULT_ARGUMENTS)

        if self.f(Flags.X_IMG):
            options.add_experimental_option(
                'prefs', {
                    'profile.managed_default_content_settings.images': 2
                })

        if self.f(Flags.X_3D):
            args.extend([
                '--disable-3d-apis',
                '--disable-flash-3d'])

        if self.f(Flags.X_OFFERS):
            args.extend([
                '--disable-offer-store-unmasked-wallet-cards',
                '--disable-offer-upload-credit-cards',
                '--disable-translate'])

        args.extend(arguments)
        for arg in args:
            options.add_argument(arg)
        if user_agent:
            options.add_argument('--user-agent=' + user_agent)
        for ext in extensions:
            options.add_extension(ext)
        c = options.to_capabilities()
        if proxy:
            proxy.add_to_capabilities(c)
        return c

    def _profile(self, arguments, extensions, proxy, user_agent):
        """ No-op for ChromeDriver. """
        self.logger.debug('building browser profile')
        return None

    def _final(self, arguments, extensions, proxy, user_agent):
        """ Configuration applied after the driver has been created.

        Args:
            arguments (list): unused.
            extensions (list): unused.
            proxy (Proxy): adds proxy instance to DesiredCapabilities.
            user_agent (str): unused.

        Returns:
            None
        """
        self.logger.debug('applying final configuration')
        return None


class ChromeVideoDriver(VideoDriver, ChromeDriver):
    """ Chrome browser inside Docker with video recording.

    Inherits from :obj:`~selenium_docker.drivers.VideoDriver`.
    """
    CONTAINER = dict(
        image='standalone-chrome-ffmpeg',
        detach=True,
        labels={'role': 'browser',
                'dynamic': 'true',
                'browser': 'chrome',
                'hub': 'false'},
        mem_limit='700mb',
        ports={DockerDriverBase.SELENIUM_PORT: None},
        publish_all_ports=True)
