# Docker files for the SUMMA ASR Module

This Repository contains Docker- and Makefiles to build production
images for the SUMMA ASR Module. The build process is a two-stage process.
First we build an image that creates a dpkg file with most things
that are needed to run the summa ASR engine in production.

```
make builder
```

Then we build a second image with only the things that are needed to
run the ASR engine in production.

```
make engine
```

The second image (`summaplatform/asr-engine`) is the one that should
be made available on dockerhub. 

