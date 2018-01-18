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
import time
from abc import abstractmethod
from collections import Mapping
from functools import partial, wraps

import docker
import gevent
from docker.errors import APIError, DockerException, NotFound
from docker.models.containers import Container
from six import string_types

from selenium_docker.errors import DockerError, SeleniumDockerException
from selenium_docker.utils import gen_uuid


def check_engine(fn):
    """ Pre-check our engine connection by sending a ping before our
    intended operation.

    Args:
        fn (Callable): wrapped function.

    Returns:
        Callable

    Example::

        @check_engine
        def do_something_with_docker(self):
            # will raise APIError before getting here
            #  if there's a problem with the Docker Engine connection.
            return True
    """

    @wraps(fn)
    def inner(self, *args, **kwargs):
        self.logger.debug('pinging docker engine')
        try:
            self.docker.ping()
        except SeleniumDockerException as e:  # pragma: no cover
            self.logger.exception(e, exc_info=True)
            raise e
        else:
            self.logger.debug('pass')
            return fn(self, *args, **kwargs)
    return inner


class ContainerInterface(object):
    """ Required functionality for implementing a custom object that has an
    underlying container.
    """

    CONTAINER = None

    def __str__(self):
        return '<%s(image=%s)>' % (
            self.__class__.__name__, self.CONTAINER.get('image', 'None'))

    @abstractmethod
    def _make_container(self):
        raise NotImplementedError

    @abstractmethod
    def close_container(self):
        raise NotImplementedError

    @abstractmethod
    def quit(self):
        raise NotImplementedError


class ContainerFactory(object):
    """ Used as an interface for interacting with Container instances.

    Example::

        from selenium_docker.base import ContainerFactory

        factory = ContainerFactory.get_default_factory('reusable')
        factory.stop_all_containers()

    Will attempt to connect to the local Docker Engine, including the word
    ``reusable`` as part of each new container's name. Calling
    ``factory.stop_all_containers()`` will stop and remove containers assocated
    with that namespace.

    Reusing the same ``namespace`` value will allow the factory to inherit
    the correct containers from Docker when the program is reset.

    Args:
        engine (:obj:`docker.client.DockerClient`): connection to the
            Docker Engine the application will interact with. If ``engine`` is
            ``None`` then :func:`docker.client.from_env` will be called to
            attempt connecting locally.
        namespace (str): common name included in all the new docker containers
            to allow tracking their status and cleaning up reliably.
        make_default (bool): when ``True`` this instance will become the
            default, used as a singleton, when requested via
            :func:`~ContainerFactory.get_default_factory`.
        logger (:obj:`logging.Logger`): logging module Logger instance.
    """

    DEFAULT = None
    """:obj:`.ContainerFactory`: singleton instance to a container factory
    that can be used to spawn new containers accross a single connected
    Docker engine.
    
    This is the instance returned by 
    :func:`~ContainerFactory.get_default_factory`. 
    """

    __slots__ = ('_containers', '_engine', '_ns', 'logger')

    def __init__(self, engine, namespace, make_default=True, logger=None):
        self._containers = {}
        self._engine = engine or docker.from_env()
        self._ns = namespace or gen_uuid(10)
        self.logger = logger or logging.getLogger(
            '%s.ContainerFactory.%s' % (__name__, self._ns))

        if make_default and ContainerFactory.DEFAULT is None:
            ContainerFactory.DEFAULT = self

        if namespace:
            # we supplied the namespace, we can bootstrap our
            #  tracked containers back from the environment
            self._containers = self.get_namespace_containers(namespace)

    def __repr__(self):
        return '<ContainerFactory(docker=%s,ns=%s,count=%d)>' % (
            self._engine.api.base_url, self._ns, len(self._containers.keys()))

    @property
    def containers(self):
        """dict:
            :obj:`~docker.models.containers.Container` instances
            mapped by name.
        """
        return self._containers

    @property
    def docker(self):
        """:obj:`docker.client.DockerClient`:
            reference to the connected Docker engine.
        """
        return self._engine

    @property
    def namespace(self):
        """str: ready-only property for this instance's namespace,
            used for generating names.
        """
        return self._ns

    def __bootstrap(self, container, **kwargs):
        """ Adds additional attributes and functions to Container instance.

        Args:
            container (Container): instance of
                :obj:`~docker.models.containers.Container` that is being
                fixed up with expected values.
            kwargs (dict): arbitrary attribute names and their values to
                attach to the ``container`` instance.

        Returns:
            :obj:`~docker.models.containers.Container`:
                the exact instance passed in.
        """
        self.logger.debug('bootstrapping container instance to factory')
        c = container
        for k, v in kwargs.items():  # pragma: no cover
            setattr(c, k, v)
        c.started = time.time()
        c.logger = logging.getLogger('%s.%s' % (__name__, kwargs.get('name')))
        c.ns = self._ns
        return c

    def as_json(self):
        """ JSON representation of our factory metadata.

        Returns:
            dict:
                that is a :py:func:`json.dumps` compatible dictionary instance.
        """
        return {
            '_ref': str(self),
            'count': len(self.containers)
        }

    def gen_name(self, key=None):
        """ Generate the name of a new container we want to run.

        This method is used to keep names consistent as well as to ensure
        the name/identity of the ``ContainerFactory`` is included. When a
        ``ContainerFactory`` is loaded on a machine with containers already
        running with its name it'll inherit those instances to re-manage
        between application runs.

        Args:
            key (str): the identifiable portion of a container name. If one
                isn't supplied (the default) then one is randomly generated.

        Returns:
            str:
                in the format of ``selenium-<FACTORY_NAMESPACE>-<KEY>``.
        """
        return 'selenium-%s-%s' % (self._ns, key or gen_uuid(6))

    @classmethod
    def get_default_factory(cls, namespace=None, logger=None):
        """ Creates a default connection to the local Docker engine.

        This ``classmethod`` acts as a singleton. If one hasn't been made it
        will attempt to create it and attach the instance to the class
        definition. Because of this the method is the preferable way to obtain
        the default connection so it doesn't get overwritten or modified by
        accident.

        Note:
            By default this method will attempt to connect to the **local**
            Docker engine only. Do not use this when attempting to use
            a remote engine on a different machine.

        Args:
            namespace (str): use this namespace if we're creating a new
                default factory instance.
            logger (:obj:`logging.Logger`): instance of logger to attach
                to this factory instance.

        Returns:
            :obj:`~.ContainerFactory`: instance to interact with Docker engine.
        """
        if cls.DEFAULT is None:
            cls(None, namespace, make_default=True, logger=logger)
        return cls.DEFAULT

    @check_engine
    def get_namespace_containers(self, namespace=None):
        """ Glean the running containers from the environment that are
        using our factory's namespace.

        Args:
            namespace (str): word identifying ContainerFactory containers
                represented in the Docker Engine.

        Returns:
            dict:
                :obj:`~docker.models.containers.Container` instances
                mapped by name.
        """
        if namespace is None:
            namespace = self.namespace
        ret = {}
        for c in self.docker.containers.list():
            if namespace in c.name:
                ret[c.name] = c
        return ret

    @check_engine
    def load_image(self, image, tag=None, insecure_registry=False,
                   background=False):
        """ Issue a ``docker pull`` command before attempting to start/run
        containers. This could potentially increase startup time, as well
        as ensure the containers are up-to-date.

        Args:
            image (str): name of the container we're downloading.
            tag (str): tag/version of the container.
            insecure_registry (bool): allow downloading image templates from
                insecure Docker registries.
            background (bool): spawn the download in a background thread.

        Raises:
            :exc:`docker.errors.DockerException`:
                if anything goes wrong during the image template download.

        Returns:
            :obj:`docker.models.images.Image`:
                the Image controlled by the connected Docker engine.
                Containers are spawned based off this template.
        """
        if tag is None:
            tag = ''
        if isinstance(image, Mapping):
            image = image.get('image', None)
        if not isinstance(image, string_types):
            raise ValueError('cannot determine image from %s' % type(image))

        try:
            self.logger.debug('checking locally for image')
            img = self.docker.images.get(image)
        except NotFound as e:
            self.logger.debug('could not find image locally, %s', image)
        else:
            return img

        self.logger.debug('loading image, %s:%s', image, tag or 'latest')
        fn = partial(self.docker.images.pull,
                     image,
                     tag=tag,
                     insecure_registry=insecure_registry,
                     stream=True)
        if background:
            gevent.spawn(fn)
        else:
            return fn()

    @check_engine
    def scrub_containers(self, *labels):
        """ Remove **all** containers that were dynamically created.

        Args:
            labels (str): labels to include in our search for finding
                containers to scrub from the connected Docker engine.

        Returns:
            int: the number of containers stopped and removed.
        """

        def stop_remove(c):
            try:
                c.stop()
                c.remove()
            except NotFound:
                self.logger.warning('could not find container %s', c.name)

        total = 0
        self.logger.debug('scrubbing all containers by library')
        # attempt to stop all the containers normally
        self.stop_all_containers()
        labels = ['browser', 'dynamic'] + list(set(labels))
        threads = []
        found = set()
        # now close all dangling containers
        for label in labels:
            containers = self.docker.containers.list(
                filters={'label': label})
            count = len(containers)
            self.logger.debug(
                'found %d dangling containers with label %s',
                count, label)
            total += count
            for c in containers:
                if c.name not in found:
                    found.add(c.name)
                    threads.append(gevent.spawn(stop_remove, c))
        for t in reversed(threads):
            t.join()
        return total

    @check_engine
    def start_container(self, spec, **kwargs):
        """ Creates and runs a new container defined by ``spec``.

        Args:
            spec (dict): the specification of our docker container. This
                can include things such as the name, labels, image,
                restart conditions, etc. The built-in driver containers
                already have this defined in their class declaration.
            kwargs ([str, str]): additional arguments that will be added
                to ``spec``; generally dynamic attributes modifying a static
                container definition.

        Raises:
            :exc:`docker.errors.DockerException`:
                when there's any problem performing start and run on the
                container we're attemping to create.

        Returns:
            :obj:`docker.models.containers.Container`:
                the newly created and managed container instance.
        """
        if 'image' not in spec:
            raise DockerException('cannot create container without image')

        self.logger.debug('starting container')

        name = spec.get('name', kwargs.get('name', self.gen_name()))

        for key in kwargs.keys():
            if key not in spec:
                self.logger.debug('updating `%s` in spec', key)

        kw = dict(spec)
        kw.update(kwargs)
        kw['name'] = name

        try:
            container = self.docker.containers.run(**kw)
        except DockerException as e:  # pragma: no cover
            self.logger.exception(e, exc_info=True)
            raise e

        # track this container
        self._containers[name] = self.__bootstrap(container)
        self.logger.debug('started container %s', name)
        return container

    @check_engine
    def stop_all_containers(self):
        """ Remove all containers from this namespace.

        Raises:
            APIError: when there's a problem communicating with
                the Docker Engine.
            NotFound: when a tracked container cannot be found in
                the Docker Engine.

        Returns:
            None
        """
        self.logger.debug('stopping all containers')
        for name in list(self.containers.keys()):
            self.stop_container(name=name)

    @check_engine
    def stop_container(self, name=None, key=None, timeout=10):
        """ Remove an individual container by name or key.

        Args:
            name (str): name of the container.
            key (str): partial reference to the container. (Optional)
            timeout (int): time in seconds to wait before sending ``SIGKILL``
                to a running container.

        Raises:
            ValueError: when ``key`` and ``name`` are both ``None``.
            APIError: when there's a problem communicating with Docker engine.
            NotFound: when no such container by ``name`` exists.

        Returns:
            None
        """
        e = None  # type: Exception
        container = None  # type: Container
        if key and not name:
            name = self.gen_name(key=key)
        if not name:
            raise ValueError('`name` and `key` cannot both be None')
        if name not in self.containers:
            self.logger.warning('container %s is not being tracked' % name)
            # we're not tracking the container in our internal state
            #  so we need to query the docker engine and see if it's there.
            try:
                container = self.docker.containers.get(name)
            except NotFound as e:
                self.logger.error('cannot find container via docker engine')
                return container
            except APIError as e:
                self.logger.exception(e, exc_info=True)
                raise DockerError(e)
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
            raise DockerError(e)
