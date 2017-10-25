NAME := selenium-docker
PYPI_REPO ?= vivint

all: build test

build: build_chrome build_firefox

build_chrome:
	cd ./dockerfiles/standalone-chrome-ffmpeg && \
	docker build -t standalone-chrome-ffmpeg:dev .

build_firefox:
	cd ./dockerfiles/standalone-firefox-ffmpeg && \
	docker build -t standalone-firefix-ffmpeg:dev .

pypi:
	python setup.py sdist upload -r $(PYPI_REPO)

test:
	tox

.PHONY: \
	all \
	build \
	build_chrome \
	build_firefox \
	pypi \
	test