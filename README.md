# vivint-selenium-docker

Extends the `selenium` Python module with additional drivers that run inside Docker containers.

```bash
$ pip install selenium-docker
```

## Examples

#### Basic,

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

#### Blocking driver pool,

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
