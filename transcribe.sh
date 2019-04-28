#!/bin/bash
set -e
mydir=$(dirname $(realpath $0))
docker run --rm -i \
       -v ${mydir}/engine:/engine \
       -v $1:/model \
       -v $2:/$(basename $2) summaplatform/asr-engine \
       /engine/transcribe.py -m /model /$(basename $2) 

#       /engine/test_transcriber.py /model /audio.wav
