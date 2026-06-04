FROM python:3.11-slim

# powerstat (x86 RAPL) and dmidecode are optional power helpers; on a Pi the
# host's vcgencmd is mounted in (statically linked) — see docs/raspberry-pi.md.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    powerstat \
    dmidecode \
    pulseaudio-utils \
    playerctl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The power library (separate project) — installed from source.
RUN pip install --no-cache-dir "git+https://github.com/TigreGotico/powerguess.git@dev"

COPY pyproject.toml README.md ./
COPY linux2mqtt/ ./linux2mqtt/
RUN pip install --no-cache-dir .

CMD ["python", "-m", "linux2mqtt"]
