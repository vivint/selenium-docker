#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import os
import time
import tarfile
from datetime import datetime
from tempfile import NamedTemporaryFile
from shutil import move as mv

from dotmap import DotMap

from selenium_docker.drivers import DockerDriver, ChromeDriver
from selenium_docker.meta import config
from selenium_docker.utils import parse_metadata


class VideoDriver(DockerDriver):
    """ Chrome browser inside Docker with video recording of its lifetime. """

    commands = DotMap(
        stop_ffmpeg  = 'pkill ffmpeg',
        start_ffmpeg = (
            'ffmpeg -y -f x11grab -s {resolution} -framerate {fps}'
            ' -i :99+0,0 {metadata} -qp 18 -c:v libx264'
            ' -preset ultrafast {filename}'))

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
        """str: filename to apply to the extracted video stream."""
        return ('%s-docker-%s.mkv' % (self.BROWSER, self._time)).lower()

    def quit(self):
        if self.__is_recording:
            self.stop_recording(self.save_path)
        super(VideoDriver, self).quit()

    def stop_recording(self, path, shard_by_date=True, environment=None):
        """ Stops the ffmpeg video recording inside the container.

        Args:
            path (str):
            shard_by_date (bool):
            environment (dict):

        Raises:
            ValueError: when ``path`` is not an existing folder path.
            IOError: when there's a problem creating the folder for video
                recorded files.

        Returns:
            str: file path to completed recording. This value is adjusted
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

    def start_recording(self, metadata=None, environment=None):
        """ Starts the ffmpeg video recording inside the container.

        Args:
            metadata (dict): arbitrary data to attach to the video file.
            environment (dict): environment variables to inject inside the
                running container before launching ffmpeg.

        Returns:
            str: the absolute file path of the file being recorded.
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


class ChromeVideoDriver(VideoDriver, ChromeDriver):
    CONTAINER = dict(
        image='standalone-chrome-ffmpeg',
        detach=True,
        labels={'role': 'browser',
                'dynamic': 'true',
                'browser': 'chrome',
                'hub': 'false'},
        mem_limit='700mb',
        ports={DockerDriver.SELENIUM_PORT: None},
        publish_all_ports=True)
