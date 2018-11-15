#!/bin/bash
set -e
mydir=$(dirname $(realpath $0))
docker run --rm -it \
       -v ${mydir}/engine:/engine \
       -v $1:/model \
       -v $2:/audio.wav summaplatform/asr-engine \
       /engine/transcribe.py -m /model /audio.wav

#       /engine/test_transcriber.py /model /audio.wav
