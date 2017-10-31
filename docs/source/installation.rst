Installation and Dependencies
=============================

The Package
^^^^^^^^^^^

Selenium-docker and its required modules can be found on pypi and intalled
via ``pip``::

    pip install selenium-docker

For the most up to date release you can install from source::

    pip install git+git//<URL>

If the required dependancies install correctly the next step is to ensure
Docker is properly installed and configured. By default ``selenium-docker``
will attempt to connect to a Docker Engine running on the local machine.
Alternatively a remote docker engine can be used instead with additional setup
and overhead.

Installing Docker
^^^^^^^^^^^^^^^^^

The easiest way to install Docker is by following the instructions for your
preferred operating system and distribution.

Following the `official downloads and instructions <https://www.docker.com/community-edition>`__
will yield the best results.


Docker Images
^^^^^^^^^^^^^

Terminal::

    docker pull vivint/selenium-chrome-ffmpeg
    docker pull vivint/selenium-firefox-ffmpeg

Links to the Dockerfiles can be found `here <URL>`__.