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

import os
import random
import string
import subprocess
from functools import partial

import gevent
from dotmap import DotMap
from six import PY2

# compatibility
if PY2:
    _range = xrange
else:  # pragma: no cover
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
        tuple(str, int):
            IP/hostname and port.

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
        return gevent.spawn(fn)
    else:
        return fn()


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
        if v is None:
            continue
        v = str(v)
        v = ''.join([c for c in v if c in valid_chars])
        if len(v) == 0:
            continue
        text = '-metadata {key}="{value}"'.format(key=str(k).lower(), value=v)
        pieces.append(text)
    return ' '.join(pieces)
