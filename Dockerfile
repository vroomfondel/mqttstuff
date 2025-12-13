ARG python_version=3.14
ARG debian_version=trixie

FROM python:${python_version}-${debian_version}

# repeat without defaults in this build-stage
ARG python_version
ARG debian_version

RUN apt update && \
    apt -y full-upgrade && \
    apt -y install htop procps iputils-ping locales vim tini && \
    pip install --upgrade pip && \
    rm -rf /var/lib/apt/lists/*

RUN sed -i -e 's/# de_DE.UTF-8 UTF-8/de_DE.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen && \
    update-locale LC_ALL=de_DE.UTF-8 LANG=de_DE.UTF-8 && \
    rm -f /etc/localtime && \
    ln -s /usr/share/zoneinfo/Europe/Berlin /etc/localtime

# MULTIARCH-BUILD-INFO: https://itnext.io/building-multi-cpu-architecture-docker-images-for-arm-and-x86-1-the-basics-2fa97869a99b
ARG TARGETOS
ARG TARGETARCH
ARG TARGETPLATFORM
RUN echo "I'm building for $TARGETOS/$TARGETARCH :: $TARGETPLATFORM"

ARG UID=1234
ARG GID=1234
ARG UNAME=pythonuser
RUN groupadd -g ${GID} -o ${UNAME} && \
    useradd -m -u ${UID} -g ${GID} -o -s /bin/bash ${UNAME}

USER ${UNAME}

ENV PATH="/home/pythonuser/.local/bin:$PATH"
ENV PYTHONPATH=${PYTHONPATH:+${PYTHONPATH}:}/app

COPY --chown=${UID}:${GID} requirements.txt /
RUN pip3 install --no-cache-dir --upgrade -r /requirements.txt

#COPY --chown=${UID}:${GID} requirements-dev.txt /
#RUN pip3 install --no-cache-dir --upgrade -r /requirements-dev.txt

COPY --chown=${UID}:${GID} mqttstuff /app/mqttstuff
COPY --chown=${UID}:${GID} mqttcommander /app/mqttcommander

COPY --chown=${UID}:${GID} main.py config.py config.yaml Helper.py README.md /app/

WORKDIR /app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG gh_ref=gh_ref_is_undefined
ENV GITHUB_REF=$gh_ref
ARG gh_sha=gh_sha_is_undefined
ENV GITHUB_SHA=$gh_sha
ARG buildtime=buildtime_is_undefined
ENV BUILDTIME=$buildtime

ARG forwarded_allow_ips=*
ENV FORWARDED_ALLOW_IPS=$forwarded_allow_ips

# ENV TINI_SUBREAPER=yes
# ENV TINI_KILL_PROCESS_GROUP=yes
# ENV TINI_VERBOSITY=3

# https://hynek.me/articles/docker-signals/
STOPSIGNAL SIGINT

# ENTRYPOINT ["/bin/bash", "-c"]

ENTRYPOINT ["tini", "--"]

# CMD ["python", "main.py"]
CMD ["tail", "-f", "/dev/null"]

