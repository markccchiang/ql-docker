# syntax=docker/dockerfile:1
#
# Interactive QuantLib Service: ql-backend and ql-frontend, built from source
# and served together from one image on Debian 13 (trixie).
#
#     docker build -t ql-app .
#     docker run --rm -p 127.0.0.1:8080:8080 ql-app
#
# then open http://localhost:8080. nginx serves the app and its user's guide on
# 8080 and passes /ws/ through to ql-backend, which listens on loopback inside
# the container only.
#
# Both applications are cloned from GitHub at QL_BACKEND_REF and QL_FRONTEND_REF
# (main by default), submodules included -- uWebSockets, and ql-protobuf as
# proto/ in each -- so the build needs no checkout and no credentials, and this
# directory contributes nothing to it but this file. To build a local checkout
# instead, unpushed changes included (its submodules initialised):
#
#     docker build \
#         --build-context ql-backend=/path/to/ql-backend \
#         --build-context ql-frontend=/path/to/ql-frontend \
#         -t ql-app .
#
# The stages, in the order the build cache is most likely to keep them:
#
#     protobuf   Protobuf with its CMake package config, which Debian's does not ship
#     quantlib   QuantLib built with QL_ENABLE_SESSIONS and without OpenMP
#     schema     a check that both applications were written against one ql-protobuf
#     backend    the ql-backend daemon, linked statically against both libraries
#     frontend   the Vite bundle
#     guide      the Sphinx user's guide, English and Traditional Chinese
#     (final)    nginx, tini and the three artefacts

ARG DEBIAN_RELEASE=trixie
# The base images by digest, and Protobuf and QuantLib below by commit: a tag
# can be moved, and what this image is built from should not change under a
# build nobody changed. All three digests are multi-platform indexes, so the
# same pins serve linux/amd64 and linux/arm64. Each moves deliberately:
#
#     docker buildx imagetools inspect debian:trixie-slim --format '{{json .Manifest.Digest}}'
#     git ls-remote https://github.com/lballabio/QuantLib.git 'refs/tags/v1.43^{}'
#
# A new DEBIAN_RELEASE needs all three digests with it.
ARG DEBIAN_DIGEST=sha256:e27e3dbef3b2064bed82f2fef343c0d02a4b8d5675e5b2c511883442e001630d
ARG NODE_DIGEST=sha256:2f13dd46eb15bfbf653ca14b6f3fa11647582379086256016cfa54017368caf6
ARG PYTHON_DIGEST=sha256:59d365aafe9c497e90af2caf4affe3e57f677328b251945b0327807887ed3772

# The applications are not pinned: a ref names a branch or a tag on purpose, so
# a release image is built with both set to its tags. BuildKit resolves a ref on
# every build, so a new commit on it is picked up without --no-cache.
ARG QL_BACKEND_REPO=https://github.com/markccchiang/ql-backend.git
ARG QL_BACKEND_REF=main
ARG QL_FRONTEND_REPO=https://github.com/markccchiang/ql-frontend.git
ARG QL_FRONTEND_REF=main

# The two sources, each a clone with its submodules. --build-context
# ql-backend=... or ql-frontend=... replaces the stage outright.
FROM scratch AS ql-backend
ARG QL_BACKEND_REPO
ARG QL_BACKEND_REF
ADD ${QL_BACKEND_REPO}#${QL_BACKEND_REF} /

FROM scratch AS ql-frontend
ARG QL_FRONTEND_REPO
ARG QL_FRONTEND_REF
ADD ${QL_FRONTEND_REPO}#${QL_FRONTEND_REF} /

# ---------------------------------------------------------------------------
FROM debian:${DEBIAN_RELEASE}-slim@${DEBIAN_DIGEST} AS toolchain
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential cmake ninja-build git ca-certificates libboost-dev \
 && rm -rf /var/lib/apt/lists/*
# Empty means one job per CPU. A QuantLib translation unit can take a gigabyte
# to compile, so a Docker VM short of memory wants a smaller number here.
ARG BUILD_JOBS=

# ---------------------------------------------------------------------------
FROM toolchain AS protobuf
# The release ql-backend is developed against. The generated code and the
# library it links have to come from the same one, and both come from here.
ARG PROTOBUF_VERSION=34.0
ARG PROTOBUF_COMMIT=6a6cd88c262ffdb1738167a47d5fcc7a3eb4edac
ADD --checksum=${PROTOBUF_COMMIT} https://github.com/protocolbuffers/protobuf.git#v${PROTOBUF_VERSION} /src/protobuf
# Abseil is fetched at the version this release pins and installed beside it,
# where find_package(Protobuf CONFIG) looks for it. C++17 to match ql-backend:
# abseil's string_view is a different type under a different standard.
RUN cmake -S /src/protobuf -B /build/protobuf -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/protobuf \
        -DCMAKE_CXX_STANDARD=17 \
        -Dprotobuf_BUILD_TESTS=OFF \
        -Dprotobuf_FORCE_FETCH_DEPENDENCIES=ON \
 && cmake --build /build/protobuf --parallel ${BUILD_JOBS:-$(nproc)} \
 && cmake --install /build/protobuf \
 && rm -rf /build/protobuf

# ---------------------------------------------------------------------------
FROM toolchain AS quantlib
# ql-backend's third_party/QuantLib pin.
ARG QUANTLIB_VERSION=1.43
ARG QUANTLIB_COMMIT=6b57206e04598f092efee66e3b367efc84771995
ADD --checksum=${QUANTLIB_COMMIT} https://github.com/lballabio/QuantLib.git#v${QUANTLIB_VERSION} /src/QuantLib
# Sessions on and OpenMP off are the two settings ql-backend cannot be correct
# without. Static, so the daemon carries its QuantLib rather than depending on
# a library the final image would need.
RUN cmake -S /src/QuantLib -B /build/QuantLib -G Ninja -Wno-dev \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/quantlib \
        -DBUILD_SHARED_LIBS=OFF \
        -DQL_ENABLE_SESSIONS=ON \
        -DQL_ENABLE_OPENMP=OFF \
        -DQL_BUILD_EXAMPLES=OFF \
        -DQL_BUILD_TEST_SUITE=OFF \
        -DQL_BUILD_BENCHMARK=OFF \
 && cmake --build /build/QuantLib --parallel ${BUILD_JOBS:-$(nproc)} \
 && cmake --install /build/QuantLib \
 && rm -rf /build/QuantLib

# ---------------------------------------------------------------------------
# Each application pins ql-protobuf as its own submodule, and the two halves
# only understand each other if those pins agree. Nothing else would notice
# that they do not: both halves would build, and the service would refuse or
# misread the page's messages at run time.
FROM toolchain AS schema
COPY --from=ql-backend proto /schema/ql-backend
COPY --from=ql-frontend proto /schema/ql-frontend
RUN for side in ql-backend ql-frontend; do \
        test -f /schema/$side/quantlib/v2/envelope.proto \
     || { echo "$side/proto is empty: run git submodule update --init --recursive there" >&2; exit 1; }; \
    done \
 && diff -r /schema/ql-backend/quantlib /schema/ql-frontend/quantlib >&2 \
 || { echo "ql-backend and ql-frontend pin different ql-protobuf commits: build refs that agree" >&2; exit 1; } \
 && touch /schema/agreed

# ---------------------------------------------------------------------------
FROM toolchain AS backend
COPY --from=protobuf /opt/protobuf /opt/protobuf
COPY --from=quantlib /opt/quantlib /opt/quantlib
# What the build reads, and nothing else: not a local build tree, not the docs.
COPY --from=ql-backend CMakeLists.txt /src/ql-backend/CMakeLists.txt
COPY --from=ql-backend src /src/ql-backend/src
COPY --from=ql-backend proto /src/ql-backend/proto
COPY --from=ql-backend third_party/uWebSockets /src/ql-backend/third_party/uWebSockets
# An empty uWebSockets configures cleanly and only skips the daemon, so it is
# caught here with the command that fixes it.
RUN test -f /src/ql-backend/third_party/uWebSockets/uSockets/src/libusockets.h \
 || { echo "ql-backend/third_party/uWebSockets is empty: run git submodule update --init --recursive there" >&2; exit 1; }
RUN cmake -S /src/ql-backend -B /build/ql-backend -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_PREFIX_PATH="/opt/quantlib;/opt/protobuf" \
 && cmake --build /build/ql-backend --target ql-backend --parallel ${BUILD_JOBS:-$(nproc)} \
 && strip /build/ql-backend/ql-backend

# ---------------------------------------------------------------------------
FROM node:22-${DEBIAN_RELEASE}-slim@${NODE_DIGEST} AS frontend
WORKDIR /src
COPY --from=ql-frontend package.json package-lock.json ./
# No install scripts: `prepare` would generate the bindings before the schema is
# copied in and set up git hooks in a tree with no git. `npm run build` below
# generates the bindings itself.
RUN npm ci --ignore-scripts
# A local checkout brings its own node_modules, dist and generated bindings
# unless its .dockerignore keeps them out; the ones built here win either way.
COPY --from=ql-frontend . .
RUN rm -rf dist src/gen
# A path, so the page dials the host it was served from.
ARG VITE_WS_URL=/ws/
RUN VITE_WS_URL="$VITE_WS_URL" npm run build

# ---------------------------------------------------------------------------
FROM python:3.13-slim-${DEBIAN_RELEASE}@${PYTHON_DIGEST} AS guide
WORKDIR /src
COPY --from=ql-frontend doc/requirements.txt doc/requirements.txt
RUN pip install --no-cache-dir -r doc/requirements.txt
# doc/conf.py takes its logo and favicon from ../assets/logo.
COPY --from=ql-frontend assets/logo assets/logo
COPY --from=ql-frontend doc doc
RUN rm -rf doc/_build doc/.venv
# Warnings are errors: a missing file (a logo, an image, a page) is only a
# warning to Sphinx, and the guide would ship without it. --keep-going lists
# every warning before failing rather than the first.
RUN sh doc/build.sh -q -W --keep-going

# ---------------------------------------------------------------------------
FROM debian:${DEBIAN_RELEASE}-slim@${DEBIAN_DIGEST}
RUN apt-get update \
 && apt-get install -y --no-install-recommends nginx tini curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --no-create-home --shell /usr/sbin/nologin ql

ARG QL_BACKEND_REPO
ARG QL_BACKEND_REF
ARG QL_FRONTEND_REPO
ARG QL_FRONTEND_REF
LABEL org.opencontainers.image.title="Interactive QuantLib Service" \
      org.opencontainers.image.description="ql-backend and ql-frontend: QuantLib pricing in the browser" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/markccchiang/ql-docker" \
      io.github.markccchiang.ql-backend.ref="${QL_BACKEND_REPO}#${QL_BACKEND_REF}" \
      io.github.markccchiang.ql-frontend.ref="${QL_FRONTEND_REPO}#${QL_FRONTEND_REF}"

# Not used at run time; copying it is what makes the schema check part of the build.
COPY --from=schema /schema/agreed /usr/share/ql-app/schema-agreed
COPY --from=backend /build/ql-backend/ql-backend /usr/local/bin/ql-backend
COPY --from=frontend /src/dist /srv/ql-frontend
# Where the status bar's Guide button looks for it (VITE_DOCS_URL's default).
COPY --from=guide /src/doc/_build/html /srv/ql-frontend/doc/_build/html
# ql-frontend's own proxy configuration and process supervisor, so the image
# runs the two processes the way that repository documents and tests them.
COPY --from=ql-frontend docker/nginx.conf /etc/ql-frontend/nginx.conf
COPY --from=ql-frontend --chmod=755 docker/entrypoint.sh /usr/local/bin/ql-entrypoint

# The browser origins ql-backend accepts, space-separated. The defaults cover
# `-p 8080:8080` reached as localhost or 127.0.0.1; publish another port or
# serve it under another name and this has to say so, or the page is refused
# (and the status bar says "running, but refusing this page"). "*" accepts any.
ENV QL_ALLOWED_ORIGINS="http://localhost:8080 http://127.0.0.1:8080"

USER ql
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD curl -fsS http://127.0.0.1:8080/ws/healthz >/dev/null || exit 1
# tini reaps and forwards signals; the entrypoint runs the two processes, and
# any arguments to `docker run` are passed on to ql-backend.
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/ql-entrypoint"]
