ARG KEA_VERSION=1.7.2
ARG LOG4CPLUS_VERSION=1.2.x
FROM alpine:3.10.3 AS build
ARG KEA_VERSION
ARG LOG4CPLUS_VERSION

RUN apk add --update --no-cache \
        curl \
        gzip \
        wget \
        build-base \
        boost-dev \
        zlib-dev \
        git \
        cmake \
        autoconf \
        automake \
        ca-certificates \ 
        bzip2-dev \
        libtool \
        libressl-dev \
        sqlite-dev 

RUN wget https://github.com/log4cplus/log4cplus/archive/${LOG4CPLUS_VERSION}.zip -O /${LOG4CPLUS_VERSION}.zip \
    && unzip /${LOG4CPLUS_VERSION}.zip -d / \
    && rm /${LOG4CPLUS_VERSION}.zip \
    && cd /log4cplus-${LOG4CPLUS_VERSION} \
    && ./configure \
    && make \
    && make install 

RUN cd / \
#    && git clone https://github.com/NEONScience/kea \
    && git clone https://github.com/sjbonarrigo/kea \
    && cd /kea \
    && git checkout badclient-workaround-${KEA_VERSION} \
    && cp -r patch/* ../. \
    && autoreconf --install \
    && ./configure --enable-shell --enable-generate-messages \
    &&  make \
    &&  make install 

RUN cd / \
    && git clone https://github.com/zorun/kea-hook-runscript \
    && cd /kea-hook-runscript \
    && make KEA_MSG_COMPILER=/usr/local/bin/kea-msg-compiler KEA_INCLUDE=/usr/local/include/kea KEA_LIB=/usr/local/lib \
    && cp kea-hook-runscript.so /usr/local/lib/. \
    && rm -rf /var/cache/apk/*

FROM alpine:3.10.3 
COPY --from=build /usr/local/bin /usr/local/bin
COPY --from=build /usr/local/etc /usr/local/etc
COPY --from=build /usr/local/lib /usr/local/lib
COPY --from=build /usr/local/sbin /usr/local/sbin
COPY --from=build /usr/local/share /usr/local/share
COPY --from=build /usr/local/var /usr/local/var
COPY ./entrypoint.sh /
COPY ./kea-dhcp4.conf /usr/local/etc/kea/
COPY ./keaevent.sh /
COPY ./clean_leases.sh /
RUN apk add --no-cache \
        bash ca-certificates curl less procps \
        boost bzip2 libressl sqlite zlib \
        mosquitto-clients python3 && \
    rm -rf /var/cache/apk/* && \
    chmod +x /entrypoint.sh && \
    chmod +x /keaevent.sh && \
    chmod +x /clean_leases.sh 
ENTRYPOINT ["/entrypoint.sh"]

