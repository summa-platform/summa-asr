FROM summaplatform/asr-engine
ARG MODEL_URL
ENV MODEL_URL=$MODEL_URL

# support for unicode in docker
# https://github.com/docker-library/python/issues/13#issue-43852823
ENV LANG C.UTF-8
# for unbuffered stdout
ENV PYTHONUNBUFFERED y

WORKDIR /
RUN bash /opt/app/download_models.sh && rm model/model.zip

WORKDIR /opt/app/
# alternative approach to unbuffered stdout, not necessary if PYTHONUNBUFFERED is defined
CMD ["/usr/bin/env", "python3", "-u", "/opt/app/rabbitmq.py"]

