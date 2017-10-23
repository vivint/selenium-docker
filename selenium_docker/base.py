#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import time
import logging
from functools import partial, wraps
from collections import Mapping

import docker
import gevent
from six import string_types
from docker.errors import APIError, DockerException, NotFound
from docker.models.containers import Container

from selenium_docker.utils import gen_uuid


def check_container(fn):
    """ Ensure we're not trying to double up an external container
        with a Python instance that already has one. This would create
        dangling containers that may not get stopped programmatically.
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


class ContainerFactory(object):
    DEFAULT = None

    def __init__(self, engine, namespace, make_default=True, logger=None):
        self._containers = {}
        self._engine = engine or docker.from_env()
        self._ns = namespace or gen_uuid(8)
        self.logger = logger or logging.getLogger(
            '%s.ContainerFactory.%s' % (__name__, self._ns))

        if make_default and ContainerFactory.DEFAULT is None:
            ContainerFactory.DEFAULT = self

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

    @classmethod
    def get_default_factory(cls, logger=None):
        if cls.DEFAULT is None:
            cls(None, None, make_default=True, logger=logger)
        return cls.DEFAULT

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
        return 'selenium-%s-%s' % (self._ns, key or gen_uuid(6))

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
        if tag is None:
            tag = ''
        if isinstance(image, Mapping):
            image = image.get('image', None)
        if not isinstance(image, string_types):
            raise ValueError('cannot determine image from %s' % type(image))

        self.logger.debug('loading image, %s:%s', image, tag or 'latest')

        fn = partial(self.docker.images.pull,
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

        name = spec.get('name', kwargs.get('name', self._gen_name()))

        kw = dict(spec)
        kw.update(kwargs)
        kw['name'] = name

        try:
            container = self.docker.containers.run(**kw)
        except DockerException as e:
            self.logger.exception(e, exc_info=True)
            raise e

        # track this container
        self._containers[name] = self.__bootstrap(container)
        self.logger.debug('started container %s', name)
        return container

    def stop_container(self, name=None, key=None, timeout=10):
        """ Remove an individual container by name or key.

        Args:
            name (str): name of the container.
            key (str): partial reference to the container. (Optional)
            timeout (int): time in seconds to wait before sending ``SIGKILL``
                to a running container.

        Raises:
            ValueError: when ``key`` and ``name`` are both None.
            APIError: when there's a problem communicating with Docker engine.
            NotFound: when no such container by ``name`` exists.

        Returns:
            None
        """
        e = None    # Exception
        if key and not name:
            name = self._gen_name(key=key)
        if not name:
            raise ValueError('`name` and `key` cannot both be None')
        if name not in self.containers:
            self.logger.warning('container %s is not being tracked' % name)
            # we're not tracking the container in our internal state
            #  so we need to query the docker engine and see if it's there.
            try:
                container = self.docker.containers.get(name)
            except (APIError, NotFound) as e:
                self.logger.error('cannot find container via docker engine')
                self.logger.exception(e, exc_info=True)
                raise e
        else:
            container = self.containers.pop(name)
        if e is not None:
            # if we couldn't get a reference to the container through our
            #  Factory instance alert that; it means we're leaking Container
            #  references.
            self.logger.info('container recovered from engine, not instance')
        self.logger.debug('stopping container %s', name)
        try:
            container.stop(timeout=timeout)
            container.remove(force=True)
        except APIError as e:
            self.logger.error('could not stop container %s', container.name)
            self.logger.exception(e, exc_info=True)
            raise e

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
            containers = self.docker.containers.list(
                filters={'label': label})
            self.logger.debug(
                'found %d dangling containers with label %s',
                len(containers), label)
            for c in containers:
                c.stop()
                c.remove()
