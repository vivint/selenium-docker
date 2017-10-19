#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

from selenium.webdriver import (
    ChromeOptions, FirefoxProfile, DesiredCapabilities)

from selenium_docker.base import DockerDriver


class ChromeDocker(DockerDriver):
    BROWSER = 'Chrome'
    CONTAINER = dict(
        image='selenium/standalone-chrome',
        detach=True,
        labels={'browser': 'chrome', 'hub': 'true'},
        mem_limit='480mb',
        ports={DockerDriver.SELENIUM_PORT: None},
        publish_all_ports=True)
    DEFAULT_ARGUMENTS = [
        '--disable-translate',
        '--start-maximized'
    ]

    def _capabilities(self, arguments, extensions, proxy, user_agent):
        # type: (list, list, Proxy, str) -> dict
        options = ChromeOptions()
        options.add_experimental_option(
            'prefs', {'profile.managed_default_content_settings.images': 2})
        args = list(self.DEFAULT_ARGUMENTS)
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

    def _profile(self, *args):
        return None


# class ChromeHubNodeDocker(HubDriver, ChromeDocker):
#     def __init__(self, *args, **kwargs):
#         self._hub = kwargs.pop('hub')
#         self._link_name = getattr(self._hub, '_name', self._hub)
#         self.CONTAINER = ChromeDocker.CONTAINER.copy()
#         self.CONTAINER.update(dict(
#             image='selenium/node-chrome',
#             labels={'browser': 'chrome', 'hub': 'true'},
#             links={self._link_name: 'hub'}
#         ))
#         super(ChromeHubNodeDocker, self).__init__(*args, **kwargs)


class FirefoxDocker(DockerDriver):
    BROWSER = 'Firefox'
    CONTAINER = dict(
        image='selenium/standalone-firefox',
        detach=True,
        labels={'browser': 'firefox', 'hub': 'true'},
        mem_limit='480mb',
        ports={DockerDriver.SELENIUM_PORT: None},
        publish_all_ports=True)
    DEFAULT_ARGUMENTS = [
        ('browser.startup.homepage', 'about:blank')
    ]

    def _capabilities(self, arguments, extensions, proxy, user_agent):
        # type: (list, list, Proxy, str) -> dict
        c = DesiredCapabilities.FIREFOX.copy()
        if proxy:
            proxy.add_to_capabilities(c)
        return c

    def _profile(self, arguments, extensions, proxy, user_agent):
        # type: (list, list, Proxy, str) -> FirefoxProfile
        profile = FirefoxProfile()
        for ext in extensions:
            profile.add_extension(ext)
        args = list(self.DEFAULT_ARGUMENTS)
        args.extend(arguments)
        for arg_k, value in args:
            profile.set_preference(arg_k, value)
        if user_agent:
            profile.set_preference('general.useragent.override', user_agent)
        return profile


# class FirefoxHubNodeDocker(HubDriver, FirefoxDocker):
#     def __init__(self, *args, **kwargs):
#         self._hub = kwargs.pop('hub')
#         self._link_name = getattr(self._hub, '_name', self._hub)
#         self.CONTAINER = FirefoxDocker.CONTAINER.copy()
#         self.CONTAINER.update(dict(
#             image='selenium/node-firefox',
#             labels={'browser': 'firefox', 'hub': 'true'},
#             links={self._link_name: 'hub'}
#         ))
#         super(FirefoxHubNodeDocker, self).__init__(*args, **kwargs)
