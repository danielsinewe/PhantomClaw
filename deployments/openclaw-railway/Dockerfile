FROM colemandunn/openclaw_railway_optimized:latest

USER root

RUN apt-get update \
  && apt-get install -y --no-install-recommends wget ca-certificates fonts-liberation \
  && wget -O /tmp/google-chrome-stable_current_amd64.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
  && apt-get install -y --no-install-recommends /tmp/google-chrome-stable_current_amd64.deb \
  && rm -rf /var/lib/apt/lists/* /tmp/google-chrome-stable_current_amd64.deb

ENV BROWSER=/usr/bin/google-chrome-stable \
    CHROME_BIN=/usr/bin/google-chrome-stable

COPY scripts/patch-wrapper-ws-proxy.js /usr/local/bin/patch-wrapper-ws-proxy.js

RUN node /usr/local/bin/patch-wrapper-ws-proxy.js
