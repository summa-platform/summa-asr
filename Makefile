# -*- mode: makefile-gmake; indent-tabs-mode: true; tab-width: 4 -*-
SHELL = bash

LANG = ar
# Take note that the model URL is currently a fake and won't work.
# This will be corrected once it is clear which ASR models can be made
# available to the general public. [UG]
ar.MODEL_URL = "http://download.summa-project.eu/models/asr/ar-v3.zip"
ar.MODEL_VERSION = v3

.PHONY: builder engine
builder: TAG=summaplatform/asr-builder
builder:
	docker build -t ${TAG} --pull builder

engine: TAG=summaplatform/asr-engine
engine: 
	docker build -t ${TAG} engine --no-cache

define build_asr_image

build: build.$1

build.$1: TAG = summaplatform/asr-$1-$${$1.MODEL_VERSION}
build.$1: URL = ${$1.MODEL_URL}
build.$1:
	docker build -t $${TAG} --build-arg MODEL_URL=$${URL} engine_with_model

endef

$(foreach L,${LANG},$(eval $(call build_asr_image,$L)))

