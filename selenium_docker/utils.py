#! /usr/bin/env python
# -*- coding: utf-8 -*-
# >>
#     vivint-selenium-docker, 2017
# <<

import os
import string
import random
import subprocess
from functools import partial, wraps

import gevent
from six import PY2
from dotmap import DotMap

__references = {}

# compatibility
if PY2:
    _range = xrange
else:
    _range = range


def gen_uuid(length=4):
    """ Generate a random ID.

    Args:
        length (int): length of generated ID.

    Returns:
        str: of length ``length``.
    """
    if not isinstance(length, int):
        length = 4
    length = max(0, length)
    return ''.join([random.choice(string.hexdigits) for _ in _range(length)])


def in_container():
    """ Determines if we're running in an lxc/docker container.

    Checks in various locations with different methods. If any one of these
    default operations are successful the function returns ``True``. This is
    not an infallible method and can be faked easy.

    Returns:
        bool
    """
    out = subprocess.check_output('cat /proc/1/sched', shell=True)
    out = out.decode('utf-8').lower()
    checks = [
        'docker' in out,
        '/lxc/' in out,
        out.split()[0] not in ('systemd', 'init',),
        os.path.exists('/.dockerenv'),
        os.path.exists('/.dockerinit'),
        os.getenv('container', None) is not None
    ]
    return any(checks)


def ip_port(container, port):
    """ Returns an updated HostIp and HostPort from the container's
    network properties. Calls container reload on-call.

    Args:
        container (Container):
        port (str):

    Returns:
        (str, int)
    """
    # make sure it's running, get the newest values
    port = str(port)
    container.reload()
    attr = DotMap(container.attrs)
    conn = attr.NetworkSettings.Ports[port][0]
    return conn.HostIp, int(conn.HostPort)


def load_docker_image(_docker, image, tag=None, insecure_registry=False,
                      background=False):
    """ Issue a `docker pull` command before attempting to start/run
    containers. This could potentially alliviate startup time, as well
    as ensure the containers are up-to-date.

    Args:
        _docker (DockerClient):
        image (str):
        tag (str):
        insecure_registry (bool):
        background (bool):

    Returns:
        Image
    """
    if tag is None:
        tag = ''
    fn = partial(_docker.images.pull,
                 image,
                 tag=tag,
                 insecure_registry=insecure_registry)
    if background:
        gevent.spawn(fn)
    else:
        return fn()


def memoize(key):
    """ Simple function caching.

    Args:
        key (str):

    Returns:
        Callable
    """
    memo = {}

    def inner(fn):
        @wraps(fn)
        def wrapped(*args):
            if key in memo:
                ret = memo[key]
            else:
                ret = memo.setdefault(key, fn(*args))
            return ret
        return wrapped
    return inner


def parse_metadata(meta):
    """ Convert a dictionary into proper formatting for ffmpeg.

    Args:
        meta (dict): data to convert.

    Returns:
        str: post-formatted string generated from ``meta``.
    """
    NO_CHR = '\'"'
    valid_chars = [c for c in string.printable if c not in NO_CHR]
    pieces = []
    for k, v in meta.items():
        v = ''.join([c for c in v if c in valid_chars])
        if len(v) == 0:
            continue
        text = '-metadata {key}="{value}"'.format(key=str(k).lower(), value=v)
        pieces.append(text)
    return ' '.join(pieces)


def ref_counter(key, direction, callback_fn=None):
    """ Counts the references for a given key.

    Args:
        key (str):
        direction (int):
        callback_fn (Callable):

    Returns:
        Callable
    """
    def inner(fn):
        @wraps(fn)
        def wrap(*args, **kwargs):
            __references[inner.key] += inner.direction
            ret_value = fn(*args, **kwargs)
            if __references[inner.key] == 0:
                inner.cb_fn(inner.key)
            return ret_value
        return wrap
    __references.setdefault(key, 0)
    inner.key = key
    inner.direction = direction
    inner.cb_fn = callback_fn or (lambda k: k)
    return inner


def references():
    """ Read-only copy of the reference counter dictionary.

    Returns:
        dict
    """
    return dict(__references.items())
