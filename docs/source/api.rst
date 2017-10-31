API
===

Base
----

.. autoclass:: selenium_docker.base.ContainerFactory
   :members:

.. autoclass:: selenium_docker.base.ContainerInterface
   :members:

.. autofunction:: selenium_docker.base.check_engine

Drivers
-------

Base
~~~~

.. autoclass:: selenium_docker.drivers.DockerDriverBase
   :members:

.. autofunction:: selenium_docker.drivers.check_container

Video Base
~~~~~~~~~~

.. autoclass:: selenium_docker.drivers.VideoDriver
   :members:

Proxy
~~~~~

.. autoclass:: selenium_docker.proxy.SquidProxy
   :members:

Chrome
~~~~~~

.. automodule:: selenium_docker.drivers.chrome
   :members:


Firefox
~~~~~~~

.. automodule:: selenium_docker.drivers.firefox
   :members:


Driver Pools
------------

.. automodule:: selenium_docker.pool
   :members:


Helpers
-------

.. py:currentmodule:: selenium_docker.helpers

.. autosummary::
   JsonFlags
   OperationsMixin

.. automodule:: selenium_docker.helpers
   :members:

Utils
-----

.. py:currentmodule:: selenium_docker.utils

.. autosummary::
   gen_uuid
   in_container
   ip_port
   load_docker_image
   parse_metadata

.. automodule:: selenium_docker.utils
   :members: