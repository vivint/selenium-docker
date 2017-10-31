#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import logging
import os
import tarfile
import time
from abc import abstractmethod
from datetime import datetime
from functools import wraps

import requests
from aenum import Flag
from docker.errors import APIError, DockerException
from dotmap import DotMap
from selenium.webdriver import Remote
from selenium.webdriver.common.proxy import Proxy
from six import add_metaclass
from tenacity import retry, stop_after_delay, wait_fixed
from toolz.functoolz import juxt

from selenium_docker.base import ContainerFactory, ContainerInterface
from selenium_docker.meta import config
from selenium_docker.utils import ip_port, parse_metadata


def check_container(fn):
    """ Ensure we're not trying to double up an external container
        with a Python instance that already has one. This would create
        dangling containers that may not get stopped programmatically.

        Note:
            This method is placed under ``base`` to prevent circular imports.

        Args:
            fn (Callable): wrapped function.

        Returns:
            Callable
    """

    @wraps(fn)
    def inner(self, *args, **kwargs):
        # check the instance
        self.logger.debug('checking container before creation')
        if self.factory is None:
            raise DockerException('no docker client defined as factory')
        if getattr(self, 'container', None) is not None:
            raise DockerException(
                'container already exists for this driver instance (%s)' %
                self.container.name)
        # check the specification
        if self.CONTAINER is None:
            raise DockerException('cannot create container without definition')
        # check the docker connection
        try:
            self.factory.docker.ping()
        except APIError as e:
            self.logger.exception(e, exc_info=True)
            raise e
        else:
            self.logger.debug('checking passed')
            return fn(self, *args, **kwargs)

    return inner


class DockerDriverMeta(type):
    def __init__(cls, name, bases, dct):
        super(DockerDriverMeta, cls).__init__(name, bases, dct)


@add_metaclass(DockerDriverMeta)
class DockerDriverBase(ContainerInterface, Remote):
    """ Base class for all drivers that want to implement Webdriver
    functionality that maps to a running Docker container.
    """

    BASE_URL = 'http://{host}:{port}/wd/hub'
    """str: connection URL used to bind with docker container."""

    BROWSER = 'Default'
    """str: name of the underlying browser being used. Classes that inhert
    from :obj:`~.DockerDriverBase` should overwrite this attribute."""

    CONTAINER = None
    """dict: default specification for the underlying container. This 
    definition is passed to the Docker Engine and is responsible for defining
    resources and metadata."""

    DEFAULT_ARGUMENTS = None
    """list: default arguments to apply to the WebDriver binary inside the
    Docker container at startup. This can be used for changing the user agent
    or turning off advanced features."""

    IMPLICIT_WAIT_SECONDS = 10.0
    """float: this can only be called once per WebDriver instance. The 
    value here is applied at the end of ``__init__`` to prevent the WebDriver
    instance from hanging inside the container."""

    SELENIUM_PORT = '4444/tcp'
    """str: identifier for extracting the host port that's bound to Docker's
    internal port for the underlying container. This string is in the format
    ``PORT/PROTOCOL``."""

    class Flags(Flag):
        """ Default bit flags to enable or disable all extra features. """
        DISABLED = 0
        ALL = 1

    def __init__(self, user_agent=None, proxy=None, cargs=None, ckwargs=None,
                 extensions=None, logger=None, factory=None, flags=None):
        """ Selenium compatible Remote Driver instance.

        Args:
            user_agent (str or Callable): overwrite browser's default
                user agent. If ``user_agent`` is a Callable then the result
                will be used as the user agent string for this browser
                instance.
            proxy (Proxy or SquidProxy): Proxy (or SquidProxy) instance
                that routes container traffic.
            cargs (list): container creation arguments.
            ckwargs (dict): container creation keyword arguments.
            extensions (list): list of file locations loaded as
                browser extensions.
            logger (:obj:`~logging.Logger`): logging module Logger instance.
            factory (:obj:`~selenium_docker.base.ContainerFactory`):
                abstract connection to a Docker Engine that does the primary
                interaction with starting and stopping containers.
            flags (:obj:`aenum.Flag`): bit flags used to turn advanced features
                on or off.

        Raises:
            ValueError: when ``proxy`` is an unknown/invalid value.
            Exception: when any problem occurs connecting the driver to its
                underlying container.
        """
        args = cargs or []
        ckwargs = ckwargs or {}
        extensions = extensions or []

        # create the container
        self.factory = factory or ContainerFactory.get_default_factory()
        self.factory.load_image(self.CONTAINER, background=False)

        self._name = ckwargs.setdefault('name', self.factory.gen_name())
        self.logger = logger or logging.getLogger(
            '%s.%s.%s' % (__name__, self.identity, self.name))

        self.container = self._make_container(**ckwargs)
        self._base_url = self.get_url()

        # user_agent can also be a callable function to randomly select one
        #  at instantiation time
        user_agent = user_agent() if callable(user_agent) else user_agent

        self._perform_check_container_ready()

        # figure out if we're using a proxy
        self._proxy, self._proxy_container = None, None
        if isinstance(proxy, Proxy):
            # Selenium Proxy
            self._proxy_container = None
            self._proxy = proxy
        elif hasattr(proxy, 'selenium_proxy'):
            # Container for SquidProxy, extract Selenium portion
            self._proxy_container = proxy
            self._proxy = proxy.selenium_proxy
        elif proxy is not None:
            raise ValueError('invalid proxy type, %s' % type(proxy))

        # build our web driver capabilities
        self.flags = self.Flags.DISABLED if not flags else flags
        fn = juxt(self._capabilities,
                  self._profile)
        capabilities, profile = fn(args, extensions, self._proxy, user_agent)
        try:
            # build our web driver
            super(DockerDriverBase, self).__init__(
                self._base_url, desired_capabilities=capabilities,
                browser_profile=profile, keep_alive=False)
        except Exception as e:
            self.logger.exception(e, exc_info=True)
            self.close_container()
            raise e

        # driver configuration
        self.implicitly_wait(self.IMPLICIT_WAIT_SECONDS)

    def __repr__(self):
        if not hasattr(self, 'session_id'):
            return '<%s(%s)>' % (self.identity, self._name)
        return super(DockerDriverBase, self).__repr__()

    @property
    def base_url(self):
        """str: read-only property of Selenium's base url. """
        return self._base_url

    @property
    def identity(self):
        """str: reference to the parent class' name. """
        return self.__class__.__name__

    @property
    def name(self):
        # type: () -> str
        """str: read-only property of the container's name. """
        return self._name

    @abstractmethod
    def _capabilities(self, arguments, extensions, proxy, user_agent):
        raise NotImplementedError

    @abstractmethod
    def _profile(self, arguments, extensions, proxy, user_agent):
        raise NotImplementedError

    def close_container(self):
        """ Removes the running container from the connected engine via
        :obj:`.DockerDriverBase.factory`.

        Returns:
            None
        """
        if not self.container:
            self.logger.warning('no container to stop')
            return
        self.logger.debug('closing and removing container')
        self.factory.stop_container(name=self.name)

    @check_container
    def _make_container(self, **kwargs):
        """ Create a running container on the given Docker engine.

        This container will contain the Selenium runtime, and ideally a
        browser instance to connect with.

        Args:
            **kwargs (dict): the specification of the docker container.

        Returns:
            :class:`~docker.models.containers.Container`
        """
        # ensure we don't already have a container created for this instance
        if self.container:
            self.logger.debug('container already running, returning')
            return self.container
        self.logger.debug('creating container')
        return self.factory.start_container(self.CONTAINER, **kwargs)

    def _perform_check_container_ready(self):
        """ Checks if the container is ready to use by calling a separate
        function. This function ``check_container_ready`` must manage its
        own retry logic if the check is to be performed more than once or over
        a span of time.

        Raises:
            :exc:`~docker.errors.DockerException`: when the container's
                creation and state cannot be verified.

        Returns:
            bool:
                ``True`` when ``check_container_ready()`` returns ``True``.
        """
        self.logger.debug('waiting for selenium to initialize')
        is_ready = self.check_container_ready()
        if not is_ready:
            raise DockerException('could not verify container was ready')
        self.logger.debug('container created successfully')
        return is_ready

    @retry(wait=wait_fixed(0.5), stop=stop_after_delay(10))
    def check_container_ready(self):
        """ Function that continuously checks if a container is ready.

        Note:
            This function should be wrapped in a `tenacity.retry` for
            continuously checking the status without failing.

        Raises:
            requests.RequestException: for any `requests` related exception.

        Returns:
            bool:
                ``True`` when the status is good. ``False`` if it cannot
                be verified or is in an unusable state.
        """
        self.logger.debug('checking selenium status')
        resp = requests.get(self._base_url, timeout=(1.0, 1.0))
        # retry on every exception
        resp.raise_for_status()
        return resp.status_code == requests.codes.ok

    def f(self, flag):
        """ Helper function for checking if we included a flag.

        Args:
            flag (:obj:`aenum.Flag`): instance of ``Flag``.

        Returns:
            bool: logical AND on an individual flag and a bit-flag set.

        Example::

            from selenium_docker.drivers.chrome import ChromeDriver, Flags

            driver = ChromeDriver(flags=Flags.ALL)
            driver.get('https://python.org')

            if driver.f(Flags.X_IMG):  # no images allowed
                # do something
                pass

            driver.quit()
        """
        return flag & self.flags

    def get_url(self):
        """ Extract the hostname and port from a running docker container,
        return it as a URL-string we can connect to.

        References:
            :func:`selenium_docker.utils.ip_port`

        Returns:
            str
        """
        host, port = ip_port(self.container, self.SELENIUM_PORT)
        base_url = self.BASE_URL.format(host=host, port=port)
        return base_url

    def quit(self):
        """ Alias for :func:`DockerDriverBase.close_container`.

        Generally this is called in a Selenium tests when you want to
        completely close and quit the active browser.

        Returns:
            None
        """
        self.logger.debug('browser quit')
        self.close_container()


class VideoDriver(DockerDriverBase):
    """ Chrome browser inside Docker with video recording of its lifetime.

    Args:
        path (str): directory where finished video recording should be stored.

    Attributes:
        save_path (str): directory to save video recording.
        _time (int): time stamp of when the class was instatiated.
        __is_recording (bool): flag for internal recording state.
        __recording_path (str): Docker internal path for saved files.
    """

    commands = DotMap(
        stop_ffmpeg='pkill ffmpeg',
        start_ffmpeg=(
            'ffmpeg -y -f x11grab -s {resolution} -framerate {fps}'
            ' -i :99+0,0 {metadata} -qp 18 -c:v libx264'
            ' -preset ultrafast {filename}'))
    """:obj:`dotmap.DotMap`: aliases for commands that run inside the docker
    container for starting and stopping ffmpeg.
    
    Attributes:
        start_ffmpeg: using X11 and LibX264.
        stop_ffmpeg: killing the process will correctly stop video recording.
    
    """

    def __init__(self, path, *args, **kwargs):
        super(VideoDriver, self).__init__(*args, **kwargs)
        # marker attributes
        if not os.path.isdir(path):
            raise IOError('path %s in not a directory' % path)
        self.save_path = path                   # type: str
        self._time = int(time.time())           # type: int
        self.__is_recording = False             # type: bool
        self.__recording_path = os.path.join(   # type: str
            config.ffmpeg_location, self.filename)
        if self._perform_check_container_ready():
            self.start_recording()

    @property
    def filename(self):
        """str: filename to apply to the extracted video stream.

        The filename will be formatted, ``<BROWSER>-docker-<TIMESTAMP>.mkv``.
        """
        return ('%s-docker-%s.mkv' % (self.BROWSER, self._time)).lower()

    def quit(self):
        """ Stop video recording before closing the driver instance and
        removing the Docker container.

        Returns:
            None
        """
        if self.__is_recording:
            self.stop_recording(self.save_path)
        super(VideoDriver, self).quit()

    def start_recording(self, metadata=None, environment=None):
        """ Starts the ffmpeg video recording inside the container.

        Args:
            metadata (dict): arbitrary data to attach to the video file.
            environment (dict): environment variables to inject inside the
                running container before launching ffmpeg.

        Returns:
            str:
                the absolute file path of the file being recorded, inside the
                Docker container.
        """
        if self.__is_recording:
            raise RuntimeError(
                'already recording, cannot start recording again')

        if not metadata:
            metadata = {}

        self.__is_recording = True

        for s, v in [
            ('title', self.filename),
            ('language', 'English'),
            ('encoded_by', 'docker+ffmpeg'),
            ('description',
             getattr(self, 'DESCRIPTION', config.ffmpeg_description))]:
            metadata.setdefault(s, v)

        cmd = self.commands.start_ffmpeg.format(
            resolution=config.ffmpeg_resolution,
            fps=config.ffmpeg_fps,
            metadata=parse_metadata(metadata),
            filename=self.__recording_path)
        self.logger.debug(
            'starting recording to file %s', self.__recording_path)
        self.logger.debug('cmd: %s', cmd)
        self.container.exec_run(cmd, environment=environment, detach=True)
        return self.__recording_path

    def stop_recording(self, path, shard_by_date=True, environment=None):
        """ Stops the ffmpeg video recording inside the container.

        Args:
            path (str): local directory where the video file should be stored.
            shard_by_date (bool): when ``True`` video files will be placed
                in a folder structure under ``path`` in the format of
                ``YYYY/MM/DD/<files>``.
            environment (dict): environment variables to inject inside the
                container before executing the commands to stop recording.

        Raises:
            ValueError: when ``path`` is not an existing folder path.
            IOError: when there's a problem creating the folder for video
                recorded files.

        Returns:
            str:
                file path to completed recording. This value is adjusted
                for ``shard_by_date``.
        """
        if not self.__is_recording:
            raise RuntimeError(
                'cannot stop recording, recording not in progress')

        self.container.exec_run(self.commands.stop_ffmpeg,
                                environment=environment,
                                detach=False)

        if not os.path.isdir(path):
            raise ValueError('%s is not a directory' % path)

        if shard_by_date:
            # split the final destination into a folder tree by date
            ts = datetime.fromtimestamp(self._time)
            path = os.path.join(path, str(ts.year), str(ts.month), str(ts.day))

        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except IOError as e:
                self.logger.exception(e, exc_info=True)
                raise e

        source = self.__recording_path
        destination = os.path.join(path, self.filename)
        tar_dest = '%s.tar' % destination

        stream, stat = self.container.get_archive(source)
        self.logger.debug(
            'video stats, name:%s, size:%s', stat['name'], stat['size'])
        with open(tar_dest, 'wb') as out_file:
            out_file.write(stream.data)
        if not tarfile.is_tarfile(tar_dest):
            raise RuntimeError('invalid tar file from container %s' % tar_dest)
        self.logger.debug('extracting tar archive')
        tar = tarfile.open(name=tar_dest)
        tar.extractall(path)
        os.unlink(tar_dest)
        self.__is_recording = False
        return destination
