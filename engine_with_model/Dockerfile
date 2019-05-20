ARG MODEL_IMAGE
ARG ENGINE_VERSION
FROM $MODEL_IMAGE as model
FROM summaplatform/asr-engine:${ENGINE_VERSION}
COPY --from=model /model /model
# support for unicode in docker
# https://github.com/docker-library/python/issues/13#issue-43852823
ENV LANG C.UTF-8
# for unbuffered stdout
ENV PYTHONUNBUFFERED y

WORKDIR /opt/app/
# alternative approach to unbuffered stdout, not necessary if PYTHONUNBUFFERED is defined
CMD ["/usr/bin/env", "python3", "-u", "/opt/app/rabbitmq.py"]
