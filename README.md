# vivint-selenium-docker

Extends the `selenium` Python module with additional drivers that run inside Docker containers.

```bash
$ pip install selenium-docker
```

## Examples

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