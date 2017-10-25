FROM selenium/node-chrome:latest
MAINTAINER Blake VandeMerwe <blake.vandemerwe@vivint.com>

USER root

# Additional Apps
# ===============
# x11-apps:     used for `xwd` screen capture
# imagemagick:  used to convert xwd screen dumps to png
# ratpoison:    simple window manager
# unclutter:    hides unnecessary desktop components; including the mouse

RUN apt-get update -qqy \
  && apt-get -qqy install \
    ffmpeg \
    fonts-ipafont-gothic \
    xfonts-100dpi \
    xfonts-75dpi \
    xfonts-cyrillic \
    xfonts-scalable \
    x11-apps \
    imagemagick \
    ratpoison \
    unclutter \
    python \
  && rm -rf /var/lib/apt/lists/*

COPY entry_point.sh /opt/bin/entry_point.sh
COPY ffserver.conf-orig /opt/ffserver.conf-orig
RUN chmod +x /opt/bin/entry_point.sh
RUN mkdir /recordings

ENV LIVE_STREAM false

# selenium self-contained server port
EXPOSE 4444

# ffserver live stream port
EXPOSE 8090
