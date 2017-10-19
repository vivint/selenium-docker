#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import time
import logging
from functools import partial

import docker
import gevent
from docker.errors import DockerException
from docker.models.containers import Container

from selenium_docker.utils import gen_uuid


class ContainerFactory(object):
    def __init__(self, engine, namespace, logger=None):
        self._containers = {}
        self._engine = engine or docker.from_env()
        self._ns = namespace or gen_uuid(8)
        self.logger = logger or logging.getLogger(
            '%s.ContainerFactory.%s' % (__name__, self._ns))

    def __repr__(self):
        return '<ContainerFactory(docker=%s,ns=%s,count=%d)>' % (
            self._engine.api.base_url, self._ns, len(self._containers.keys()))

    @property
    def containers(self):
        return self._containers

    @property
    def docker(self):
        return self._engine

    @property
    def namespace(self):
        return self._ns

    def __bootstrap(self, container, **kwargs):
        # type: (Container, dict) -> Container
        """ Adds additional attributes and functions to Container instance. """
        self.logger.debug('bootstrapping container instance to factory')
        c = container
        for k, v in kwargs.items():
            setattr(c, k, v)
        c.started = time.time()
        c.logger = logging.getLogger('%s.%s' % (__name__, kwargs.get('name')))
        c.ns = self._ns
        return c

    def _gen_name(self, key=None):
        # type: (str) -> str
        return 'council-%s-%s' % (self._ns, key or gen_uuid(6))

    def as_json(self):
        # type: () -> dict
        return {
            '_ref': str(self),
            'count': len(self.containers)
        }

    def load_image(self, image, tag=None, insecure_registry=False,
                   background=False, verbose=True):
        """ Issue a `docker pull` command before attempting to start/run
            containers. This could potentially alliviate startup time, as well
            as ensure the containers are up-to-date.

            Args:
                image (str):
                tag (str):
                insecure_registry (bool):
                background (bool):
                verbose (bool)

            Returns:
                Image
        """
        self.logger.debug('loading image, %s:%s', image, tag)
        if tag is None:
            tag = ''
        fn = partial(self._engine.images.pull,
                     image,
                     tag=tag,
                     insecure_registry=insecure_registry,
                     stream=verbose)
        if background:
            gevent.spawn(fn)
        else:
            return fn()

    def start_container(self, spec, **kwargs):
        # type: (dict) -> Container
        if 'image' not in spec:
            raise DockerException('cannot create container without image')

        self.logger.debug('starting container')

        name = kwargs.get('name', self._gen_name())

        kw = dict(spec)
        kw.update(kwargs)
        kw['name'] = name

        try:
            container = self._engine.containers.run(**kw)
        except DockerException as e:
            self.logger.exception(e, exc_info=True)
            raise e

        # track this container
        self._containers[name] = self.__bootstrap(container)
        self.logger.debug('started container %s', name)
        return container

    def stop_container(self, name=None, key=None):
        # type: (str, str) -> None
        """ Remove an individual container by name or key."""
        if key and not name:
            name = self._gen_name(key=key)
        if not name:
            raise ValueError('`name` and `key` cannot both be None')
        if name not in self.containers:
            raise KeyError('container %s it not being tracked' % name)
        container = self.containers.pop(name)
        self.logger.debug('stopping container %s', name)
        container.stop()
        container.remove()

    def stop_all_containers(self):
        # type: () -> None
        """ Remove all containers from this namespace. """
        self.logger.debug('stopping all containers')
        for name in self.containers.keys():
            self.stop_container(name=name)

    def scrub_containers(self, *labels):
        # type: (*str) -> None
        """ Remove ALL containers that were dynamically created. """
        self.logger.debug('scrubbing all containers by library')
        # attempt to stop all the containers normally
        self.stop_all_containers()
        labels = ['browser'] + list(set(labels))
        # now close all dangling containers
        for label in labels:
            containers = self._engine.containers.list(
                filters={'label': label})
            self.logger.debug('found %d dangling containers with label %s',
                              len(containers), label)
            for c in containers:
                c.stop()
                c.remove()
