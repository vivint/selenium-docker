NAME := selenium-docker
PYPI_REPO ?= vivint

all: build docs test

build: build_chrome build_firefox

build_chrome:
	cd ./dockerfiles/standalone-chrome-ffmpeg && \
	docker build -t standalone-chrome-ffmpeg:dev .

build_firefox:
	cd ./dockerfiles/standalone-firefox-ffmpeg && \
	docker build -t standalone-firefix-ffmpeg:dev .

docs:
	$(MAKE) -C docs html

pypi:
	python setup.py sdist upload -r $(PYPI_REPO)

test:
	python -m \
		pytest -x --showlocals --tb=long --junitxml=results.xml \
		--cov-report term-missing --cov=selenium_docker \
		tests/

.PHONY: \
	all \
	build \
	build_chrome \
	build_firefox \
	docs \
	pypi \
	test