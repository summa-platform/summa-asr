FROM ubuntu:16.04

# TO TRY at some point:
# - use apt-get install lib-openblas-dev instead of compiling
#   openblas from scratch in the builder image
# - do things still work with TARGET=NEHALEM ???

RUN apt-get update -qq && apt-get install -y \
    git bzip2 wget \
    g++ make python python3 python3-pip \
    zlib1g-dev automake autoconf libtool subversion \
    libatlas-base-dev sox && pip3 install --upgrade pip

# ARG ALEX_ASR_VERSION=8da15a7
ARG ALEX_ASR_VERSION=7ab2b0f89de468645e1d00f282aefd48ca9a314d
ARG KALDI_VERSION=40a9dc642d6c1479fde5997cc7e0d5e3577f510e
ARG OPENFST_VERSION=1.6.2
# ARG BUILD_ARCH=x86-64
ARG BUILD_ARCH=NEHALEM

WORKDIR /opt/
RUN git clone https://github.com/choko/alex-asr.git \
    && cd alex-asr && mkdir libs \
    && git clone https://github.com/kaldi-asr/kaldi.git libs/kaldi \
    && git clone https://github.com/UFAL-DSG/pyfst.git libs/pyfst 

WORKDIR /opt/alex-asr
RUN git checkout ${ALEX_ASR_VERSION} \
    && pip3 install -r requirements.txt \
    && cd libs/kaldi \
    && git checkout ${KALDI_VERSION}

WORKDIR /opt/alex-asr/libs/kaldi/tools
RUN sed -e "s/--enable-ngram-fsts/--enable-ngram-fsts --with-pic/g;s/openfst.cs.nyu.edu/openfst.org/g" -i Makefile \
    && OPENFST_VERSION=${OPENFST_VERSION} make -j openfst
RUN sed -i "s/USE_THREAD=0/USE_THREAD=0 TARGET=${BUILD_ARCH}/g" Makefile && make -j openblas
RUN make -j openblas

WORKDIR /opt/alex-asr/libs/kaldi/src
RUN ./configure --shared --use-cuda=no --openblas-root=../tools/OpenBLAS/install && make  

WORKDIR /opt/alex-asr
RUN make 

ARG VERSION
RUN VERSION=${VERSION:=$(date +%Y%m%d-%H%M%S)} \
    && echo VERSION=$VERSION >> VERSION.env \
    && echo dpkg=summa-asr-${VERSION} >> VERSION.env \
    && python3 setup.py install --root ./summa-asr-${VERSION} \
    && pip3 install webrtcvad aio-pika==0.21.0 --root ./summa-asr-${VERSION} 

RUN . ./VERSION.env && echo $VERSION \
    && find ${dpkg} -name '*.so' | xargs strip -S  \
    && mkdir -p ${dpkg}/DEBIAN \
    && echo 'Package: summa-asr' >> ${dpkg}/DEBIAN/control \
    && echo "Version: $VERSION" >> ${dpkg}/DEBIAN/control \
    && echo 'Maintainer: SUMMA Consortium' >> ${dpkg}/DEBIAN/control \
    && echo 'Description: ASR engine for the SUMMA Platform' >> ${dpkg}/DEBIAN/control \
    && echo 'Architecture: amd64' >> ${dpkg}/DEBIAN/control \
    && dpkg-deb --build ${dpkg}
    
    #&& find ./summa-asr-${VERSION} -name '*.a' | xargs strip -S  \
