NAME := selenium-docker
PYPI_REPO ?= vivint

all: build docs test

build: build_chrome build_firefox

build_chrome:
	cd ./dockerfiles/standalone-chrome-ffmpeg && \
	docker build -t standalone-chrome-ffmpeg .

build_firefox:
	cd ./dockerfiles/standalone-firefox-ffmpeg && \
	docker build -t standalone-firefox-ffmpeg .

docs:
	$(MAKE) -C docs html

pypi:
	python setup.py sdist upload -r $(PYPI_REPO)

test:
	SELENIUM_FFMPEG_FPS=10 python -m \
		pytest --showlocals --tb=long --junitxml=results.xml \
		--cov-config=.coveragerc --cov=selenium_docker tests/

.PHONY: \
	all \
	build \
	build_chrome \
	build_firefox \
	docs \
	pypi \
	test