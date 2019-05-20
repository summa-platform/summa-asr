# -*- mode: makefile-gmake; indenxot-tabs-mode: true; tab-width: 4 -*-
SHELL = bash
GITHASH=$(shell git log --pretty=format:'%h' -n 1)

# Languages for which we provide models
LANG = de es fa lv pt ru uk
de.MODEL_IMAGE=summaplatform/asr-model-de:v2
es.MODEL_IMAGE=summaplatform/asr-model-es:v1.1
fa.MODEL_IMAGE=summaplatform/asr-model-fa:v2
lv.MODEL_IMAGE=summaplatform/asr-model-lv:v1
pt.MODEL_IMAGE=summaplatform/asr-model-pt:v1
ru.MODEL_IMAGE=summaplatform/asr-model-ru:v1
uk.MODEL_IMAGE=summaplatform/asr-model-uk:v1.0

.PHONY: builder engine

# Builder is the build environment for the SUMMA ASR engine
# Normally, you should not have to re-build it unless there are
# changes in the build process for Alex-ASR / CloudASR.
builder: TAG=summaplatform/asr-builder:${GITHASH}
builder:
	docker build -t ${TAG} --pull builder

engine: TAG=summaplatform/asr-engine:${GITHASH}
engine: 
	docker build -t ${TAG} engine --no-cache

define build_engine_with_model

VERSION=$$(shell
asr-engine-$1: VERSION=$(shell echo ${$1.MODEL_IMAGE} | sed 's/.*://')
asr-engine-$1: TAG = summaplatform/asr-engine:${GITHASH}-$1-$${VERSION}
asr-engine-$1: MODEL_IMAGE = ${$1.MODEL_IMAGE}
asr-engine-$1:
	docker build -t $${TAG} \
	--build-arg MODEL_IMAGE=$${MODEL_IMAGE} \
	--build-arg ENGINE_VERSION=${GITHASH} \
	engine_with_model
	docker tag $${TAG} summaplatform/asr-$1:latest

endef

$(foreach L,${LANG},$(eval $(call build_engine_with_model,$L)))
