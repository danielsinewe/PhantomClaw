FROM colemandunn/openclaw_railway_optimized:latest

USER root

RUN apt-get update \
  && apt-get install -y --no-install-recommends wget ca-certificates fonts-liberation python3 python3-pip python3-venv \
  && wget -O /tmp/google-chrome-stable_current_amd64.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
  && apt-get install -y --no-install-recommends /tmp/google-chrome-stable_current_amd64.deb \
  && rm -rf /var/lib/apt/lists/* /tmp/google-chrome-stable_current_amd64.deb

RUN python3 -m venv /opt/phantomclaw-venv \
  && /opt/phantomclaw-venv/bin/pip install --upgrade pip \
  && /opt/phantomclaw-venv/bin/pip install "browser-use-sdk>=3.4.3" "playwright>=1.57.0" "psycopg[binary]>=3.3.3"

RUN python3 -m venv /opt/browser-use-cli-venv \
  && /opt/browser-use-cli-venv/bin/pip install --upgrade pip \
  && /opt/browser-use-cli-venv/bin/pip install "browser-use>=0.12.6" \
  && ln -sf /opt/browser-use-cli-venv/bin/browser-use /usr/local/bin/browser-use

ENV BROWSER=/usr/bin/google-chrome-stable \
    CHROME_BIN=/usr/bin/google-chrome-stable \
    PATH=/opt/phantomclaw-venv/bin:$PATH \
    PHANTOMCLAW_REPO_DIR=/opt/phantomclaw

COPY scripts/patch-wrapper-ws-proxy.js /usr/local/bin/patch-wrapper-ws-proxy.js
COPY scripts/peerlist-browser-use-cli-smoke.sh /usr/local/bin/peerlist-browser-use-cli-smoke.sh
COPY scripts/run-peerlist-follow-workflow.sh /usr/local/bin/run-peerlist-follow-workflow.sh
COPY phantomclaw /opt/phantomclaw

RUN node /usr/local/bin/patch-wrapper-ws-proxy.js
RUN chmod +x /usr/local/bin/peerlist-browser-use-cli-smoke.sh /usr/local/bin/run-peerlist-follow-workflow.sh
