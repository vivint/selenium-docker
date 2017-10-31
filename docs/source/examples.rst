Example Code
============

Cleanup
-------

Getting rid of all dynamically created containers on Docker host::

    from selenium_docker.base import ContainerFactory

    factory = ContainerFactory.get_default_factory()
    factory.scrub_containers()
