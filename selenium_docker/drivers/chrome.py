#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

from aenum import Flag, auto
from selenium.webdriver.chrome.options import Options as ChromeOptions

from selenium_docker.drivers import DockerDriverBase, VideoDriver


class ChromeDriver(DockerDriverBase):
    """ Chrome browser inside Docker. """

    class Flags(Flag):
        DISABLED    = 0
        X_IMG       = auto()
        X_3D        = auto()
        X_OFFERS    = auto()
        ALL         = ~DISABLED

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

    def _capabilities(self, arguments, extensions, proxy, user_agent):
        """ Compile the capabilities of ChromeDriver inside the Container.

        Args:
            arguments (list):
            extensions (list):
            proxy (Proxy):
            user_agent (str):

        Returns:
            ChromeOptions
        """
        options = ChromeOptions()
        args = list(self.DEFAULT_ARGUMENTS)

        if self.Flags.X_IMG & self.flags:
            options.add_experimental_option(
                'prefs', {
                    'profile.managed_default_content_settings.images': 2
                })

        if self.Flags.X_3D & self.flags:
            args.extend([
                '--disable-3d-apis',
                '--disable-flash-3d'])

        if self.Flags.X_OFFERS & self.flags:
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
        return None


class ChromeVideoDriver(VideoDriver, ChromeDriver):
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
