# vivint-selenium-docker

Extending Selenium with drop in replacements for Chrome and Firefox webdriver classes that will run inside a Docker container instead of in the user's desktop environment.

## Getting Started

1. Install the module:

    Latest stable version from pypi,

    ```bash
    $ pip install selenium-docker
    ```
    
    Development version from source,
    
    ```bash
    $ pip install git+ssh://git@source.vivint.com:7999/devops/vivint-selenium-docker.git@master
    ```

2. Download [docker](https://www.docker.com/get-docker) for your operating system and ensure it's running.

    ```bash
    $ docker version
    Client:
     Version:      17.10.0-ce
     API version:  1.33
    
    Server:
     Version:      17.10.0-ce
     API version:  1.33 (minimum version 1.12)
    ```

3. 

#### You should know...

- Calling `getLogger('selenium_docker').setLevel(logging.DEBUG)` during Logging setup will turn on lots of debug statements involved with with spawning and managing the underlying containers and driver instances.

- You can use the script below to stop and remove all running containers created by this library:

    ```python
    from selenium_docker.base import ContainerFactory
    
    factory = ContainerFactory.get_default_factory()
    factory.scrub_containers()
    ```

    This will do a search in the default Docker engine for all containers that use our `browser` and `dynamic` labels.

- We use [`gevent`](http://www.gevent.org/contents.html) for its concurrency idioms. 

- We call `gevent.monkey.patch_socket` to communicate with Docker engine via REST. Other libraries may need to be patched contingent on what your project is trying to accomplish.
  
  Read about [monkey patching](http://www.gevent.org/intro.html#monkey-patching) on the gevent website.

## Examples

#### Basic

Creates a single container with a running Chrome Driver instance inside. Connecting and managing the container is all done automatically. This should function as a drop in replacement for using the desktop version of Chrome and Firefox drivers.

```python
import sys
import logging

from selenium_docker import ChromeDriver

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.getLogger('selenium_docker').setLevel(logging.DEBUG)

driver = ChromeDriver()

driver.get('https://google.com')

print driver.title

driver.quit()
```

#### Blocking driver pool

Used for performing a single task on multiple sites/items in parallel. 

The blocking driver pool will create all the necessary containers in advance in order to distribute the work as resources become available. Drivers will be reused  until the `.execute()` call is complete. If the driver throws an Exception then that driver will be removed from the pool.

```python
from selenium_docker.pool import DriverPool


def get_title(driver, url):
    driver.get(url)
    return driver.title

urls = [
    'https://google.com',
    'https://reddit.com',
    'https://yahoo.com',
    'http://ksl.com',
    'http://cnn.com'
]

pool = DriverPool(size=3)

for result in pool.execute(get_title, urls):
    print(result)
```

#### Asynchronous driver pool,

```python
from selenium_docker.pool import DriverPool


def get_title(driver, url):
    driver.get(url)
    return driver.title

def print_fn(s):
    print s

urls = [
    'https://google.com',
    'https://reddit.com',
    'https://yahoo.com',
    'http://ksl.com',
    'http://cnn.com'
]


pool = DriverPool(size=2)
pool.execute_async(get_title, urls, print_fn)
pool.add_async(['https://facebook.com',
                'https://mail.com',
                'https://outlook.com'])

for x in pool.results():
    print('result - ', x)

    if '.com' in x:
        pool.add_async(['https://wikipedia.org'])

    if x == 'Wikipedia':
        pool.stop_async()
        pool.factory.scrub_containers()
```

## License

Copyright 2017 - Vivint, inc.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.