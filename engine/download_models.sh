#!/bin/bash
set -e

MODEL_URL=$1
path=$2

mkdir -p $path

cd $path
[ ! -f model.zip ] && [ "$MODEL_URL" != "" ] && wget "${MODEL_URL}" -O model.zip
[ -f model.zip ] && unzip -n model.zip

# Backward compatibility with old models
find . -name "*cmvn*" | xargs -I {} sed -i "s/--norm-mean=/--norm-means=/" {}

# fix an error in v3 of the arabic models
sed -i 's/^-1-/--/' alex_asr.conf
