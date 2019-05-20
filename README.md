# Docker files for the SUMMA ASR Module

This Repository contains Docker- and Makefiles to
build production images for the SUMMA ASR Module.

## Very Quick Start

The ASR engines provided here are provided as Docker images. Whatever
you do, you will have to be able to run [Docker](https://docker.io) on
your host.

The easiest way to use SUMMA ASR engine is to use
the pre-compiled Docker images. Our docker images are
designed to be used within the Open-source
[SUMMA Platform](https://github.com/summa-platform/summa-oss)
and by default act as workers on a RabbitMQ message queue.

They can be used offline as follows. Suppose you have a `.wav` file `test.wav`
in German. Then run 
```
docker run --rm -t -v /path/to/test.wav:/test.wav summaplatform/asr-de ./transcribe.py /model /test.wav
```

The output will consit of one word of transcription per line
```
<offset from start of file> <token duration> <token>
```

Currently available engines:

- German: summaplatform/asr-de
- Spanish: summaplatform/asr-es
- Farsi: summaplatform/asr-fa
- Latvian: summaplatform/asr-lv
- Portuguese: summaplatform/asr-pt
- Russian: summaplatform/asr-ru
- Ukranian: summaplatform/asr-uk

## Quick Start
To use one of the dockerized ASR engines,
you need to combine the SUMMA ASR Engine with a
specific model. Models for the following languages are
available as Docker images:

|Language|Image|
|---|---|
|German|summaplatform/asr-model-de:v2|
|Spanish|summaplatform/asr-model-es:v1.1|
|Farsi|summaplatform/asr-model-fa:v2|
|Latvian|summaplatform/asr-model-lv:v1|
|Portuguese|summaplatform/asr-model-pt:v1|
|Russian|summaplatform/asr-model-ru:v1|
|Ukrainian|summaplatform/asr-model-uk:v1.0|

The easiest way to build an image is through `make`:
```
make asr-engine-<Language Tag>
```

### Re-build the 'naked' engine (without models):

We use a staged build to build the engine image.

First, we build an image that can build the ASR engine.
This is a lengthy process, try pulling `summaplatform/asr-builder first before you build from scratch.

```
make builder
```

Once we have the build environment, we build a second image with only
the things that are needed to run the ASR engine in production.
```
make engine
```

The second image (`summaplatform/asr-engine`) is the one that should
be made available on dockerhub. 

