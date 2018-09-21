FROM summaplatform/asr-builder:latest as builder
FROM ubuntu:16.04
# This is the production image to be used in the SUMMA platform The
# ASR Engine is built in a separate container and packaged as a *.deb
# file for easier transfer to this image. We use the multi-stage
# build to reduce the size of the production image; there's no need
# to keep around the build residue.

# TO TRY at some point:
# - use an alpine image instead of Ubuntu for smaller iamge size
# - use apt-get install lib-openblas-dev instead of compiling
#   openblas from scratch in the builder image

ENV LANG C.UTF-8
ENV PYTHONUNBUFFERED y
# for unbuffered stdout

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgfortran3 \
    python3 \
    python3-pkg-resources \
    unzip \
    wget

# Note: webrtcvad aio-pika==0.21.0 are installed in the builder and
# included in the .deb file that is created there.

COPY --from=builder /opt/alex-asr/*.deb .
RUN dpkg -i *.deb && rm *.deb && rm -rf /var/lib/apt/lists/*
ADD . /opt/app
WORKDIR /opt/app

CMD ["/usr/bin/env", "python3", "-u", "/opt/app/rabbitmq.py"]
