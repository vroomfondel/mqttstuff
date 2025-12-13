![mypy and pytests](https://github.com/vroomfondel/mqttstuff/actions/workflows/mypynpytests.yml/badge.svg)
[![BuildAndPushMultiarch](https://github.com/vroomfondel/mqttstuff/actions/workflows/buildmultiarchandpush.yml/badge.svg)](https://github.com/vroomfondel/mqttstuff/actions/workflows/buildmultiarchandpush.yml)
![Cumulative Clones](https://img.shields.io/endpoint?logo=github&url=https://gist.githubusercontent.com/vroomfondel/8a315c36125952c9976548dfbf45cb7b/raw/mqttstuff_clone_count.json)
[![Docker Pulls](https://img.shields.io/docker/pulls/xomoxcc/mqttstuff?logo=docker)](https://hub.docker.com/r/xomoxcc/mqttstuff/tags)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/mqttstuff?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=PyPi+Downloads)](https://pepy.tech/projects/mqttstuff)

[![https://github.com/vroomfondel/mqttstuff/raw/main/Gemini_Generated_Image_mqttstuff_wjpr8gwjpr8gwjpr_250x250.png](https://github.com/vroomfondel/mqttstuff/raw/main/Gemini_Generated_Image_mqttstuff_wjpr8gwjpr8gwjpr_250x250.png)](https://github.com/vroomfondel/mqttstuff)

# MQTTStuff

Lightweight helper utilities for working with MQTT via Paho, with convenient wrappers for:

- Connecting and subscribing to topics, including retained-message handling
- Publishing one or many messages with consistent metadata and timestamps
- Reading “last/most recent” messages with timeout-based collection and optional type conversion
- Inspecting and commanding Tasmota devices via their MQTT topics
- Pydantic-based configuration (YAML + environment overrides)
- Developer helpers for JSON pretty-printing, deep updates, and logging configuration

- Repository: https://github.com/vroomfondel/mqttstuff
- Packages: `mqttstuff`, `mqttcommander`

## Overview

MQTTStuff provides a higher-level interface over `paho-mqtt` to simplify common patterns:

- A `MosquittoClientWrapper` to configure, connect, subscribe, and publish with minimal boilerplate
- A `MQTTLastDataReader` utility to retrieve the most recent messages for one or more topics quickly
- A `mqttcommander.tasmotacommander` toolkit to discover Tasmota devices from retained topics and interact with them in bulk
- Pydantic settings in `config.py` to load credentials and broker details from `config.yaml`/`config.local.yaml` and/or environment

The project also includes a Dockerfile for a batteries-included container image useful for testing and running these tools in a consistent environment.

## Installation

Options:

- From source (editable):
  - `python -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements-dev.txt`
  - `pip install -e .`

- Build distributions with Hatch:
  - `make pypibuild`
  - Artifacts are created under `dist/`

## Quick Start

Simple publish and subscribe using the wrapper:

```python
from mqttstuff.mosquittomqttwrapper import MosquittoClientWrapper

client = MosquittoClientWrapper(
    host="localhost", port=1883, username="user", password="pass",
    topics=["test/topic"],
)

def on_any_message(msg, userdata):
    # msg is an instance of MWMqttMessage with convenient fields
    print(msg.topic, msg.value)

client.set_on_msg_callback(on_any_message, rettype="valuemsg")
client.connect_and_start_loop_forever()

# elsewhere or in another process
client.publish_one("test/topic", {"hello": "world"}, retain=False)
```

Read last retained or recent messages with a timeout:

```python
from mqttstuff.mosquittomqttwrapper import MQTTLastDataReader

data = MQTTLastDataReader.get_most_recent_data_with_timeout(
    host="localhost", port=1883, username="user", password="pass",
    topics=["tele/+/STATE", "stat/+/STATUS"],
    retained="only",  # "yes" | "no" | "only"
    rettype="str_raw", # or "json", "valuemsg", "str", "int", "float"
)
print(data)
```

## Configuration

Configuration is defined with Pydantic Settings in `config.py` and loaded from:

1. Environment variables
2. `config.local.yaml` (if present)
3. `config.yaml`

You can override paths with environment variables:

- `MQTTSTUFF_CONFIG_DIR_PATH` – base config dir
- `MQTTSTUFF_CONFIG_PATH` – path to main YAML config
- `MQTTSTUFF_CONFIG_LOCAL_PATH` – path to local override YAML

The `Mqtt` section is expected to contain common fields like `host`, `port`, `username`, `password`, and optional topic lists. See the file headers in `config.py` for details.

## Python Modules

Each Python module provided by this repository is documented here with a focused explanation of its purpose and usage.

### Module: `mqttstuff.mosquittomqttwrapper`

Key classes and responsibilities:

- `MWMqttMessage` (Pydantic model)
  - Normalized container for incoming/outgoing MQTT messages
  - Helpers like `from_pahomsg(...)` and fields for `topic`, `qos`, `retain`, `payload`, `value`, `created_at`, and optional `metadata`

- `MosquittoClientWrapper`
  - Thin wrapper around `paho.mqtt.client.Client`
  - Simplifies connection setup and topic subscriptions via `set_topics([...])`
  - Register callbacks per-topic (`add_message_callback(topic, callback, rettype=...)`) or a global callback (`set_on_msg_callback`)
  - Publish utilities:
    - `publish_one(topic, value, created_at=None, metadata=None, rettype="valuemsg", retain=False, timeout=None)`
    - `publish_multiple(list[MWMqttMessage], timeout=None)`
  - Connection loop helpers:
    - `connect_and_start_loop_forever(topics=None, timeout_connect_seconds=None)`
    - `wait_for_connect_and_start_loop()`
  - Convenience: automatic payload conversion for int/float/str/JSON/valuemsg

- `MQTTLastDataReader`
  - Static helper to retrieve the most recent messages within a configurable timeout window
  - Supports retained-only, no-retained, or mixed operation via `retained` parameter
  - Returns results in different representations via `rettype` and `fallback_rettype`

Example – per-topic callback with type conversion:

```python
from mqttstuff.mosquittomqttwrapper import MosquittoClientWrapper

client = MosquittoClientWrapper(
    host="localhost", port=1883, username="user", password="pass",
    topics=["home/+/temperature"],
)

def on_temperature(msg, userdata):
    # msg.value is already a number if rettype="int"/"float"
    print("Temp:", msg.value)

client.add_message_callback("home/+/temperature", on_temperature, rettype="float")
client.connect_and_start_loop_forever()
```

### Module: `mqttcommander.tasmotacommander`

Tools to discover and command Tasmota devices using their MQTT topics.

Highlights:

- Data models for timers, timezone/DST config, device config and sensors
- `MqttCommander` to collect retained messages across topics, filter noisy subtrees, and start processing loops
- Discovery helpers:
  - `get_all_tasmota_devices_from_retained(...)`
  - `filter_online_tasmotas_from_retained(...)`
  - `update_online_tasmotas(...)`
- Command helpers to send one or many commands to all online devices:
  - `send_cmds_to_online_tasmotas(tasmotas, to_be_used_commands=[...], values_to_send=[...])`
- Timezone utilities to ensure consistent device settings:
  - `ensure_correct_timezone_settings_for_tasmotas(online_tasmotas)`
- JSON utilities and pretty-printers for review and persistence:
  - `write_tasmota_devices_file(...)`
  - `read_tasmotas_from_latest_file(...)`

Example – list online devices and send a command:

```python
from mqttcommander.tasmotacommander import (
    get_all_tasmota_devices_from_retained,
    filter_online_tasmotas_from_retained,
    send_cmds_to_online_tasmotas,
)

all_devs = get_all_tasmota_devices_from_retained(topics=["tele/+/STATE"], noisy=False)
online = filter_online_tasmotas_from_retained(all_devs)
send_cmds_to_online_tasmotas(online, to_be_used_commands=["Power"], values_to_send=[["Toggle"]])
```

### Module: `config`

- Centralized configuration and Loguru logging setup
- Uses `pydantic-settings` to read from environment and YAML
- Timezone helpers and constants (e.g., `TZBERLIN`)
- Environment variables `LOGURU_LEVEL`, `MQTTSTUFF_CONFIG_*` are respected

Typical usage:

```python
from config import Settings

settings = Settings()  # loads from env + config.local.yaml + config.yaml
print(settings.MQTT.host, settings.MQTT.port)
```

### Module: `Helper`

Small utilities used across the project:

- `ComplexEncoder` for JSON serialization of complex types (UUID, datetimes, dict/list pretty rendering)
- `print_pretty_dict_json`, `get_pretty_dict_json`, `get_pretty_dict_json_no_sort`
- `update_deep(base, u)` for deep dict/list merge/update
- `get_exception_tb_as_string(exc)` for converting exception tracebacks to strings
- `get_loguru_logger_info()` to introspect Loguru handlers and filters

## Docker

The repository contains a ready-to-use Dockerfile at the repository root designed for local development and CI usage.

### What the Docker image includes

- Base: `python:${python_version}-${debian_version}` (defaults `3.14-trixie`)
- Useful packages: `htop`, `procps`, `iputils-ping`, `locales`, `vim`, `tini`
- Python dependencies from `requirements.txt` and `requirements-dev.txt`
- Source code copied into `/app` and `PYTHONPATH=/app`
- Loguru-friendly environment with `tini` as entrypoint

### Build arguments

- `python_version` – default `3.14`
- `debian_version` – default `trixie`
- `UID`, `GID`, `UNAME` – user configuration in the image (defaults: 1234/1234/pythonuser)
- `TARGETOS`, `TARGETARCH`, `TARGETPLATFORM` – auto-populated by BuildKit/buildx for multi-arch
- `gh_ref`, `gh_sha`, `buildtime` – injected into environment variables (`GITHUB_REF`, `GITHUB_SHA`, `BUILDTIME`)
- `forwarded_allow_ips` – forwarded IPs for proxied setups, default `*`

### Building the image

Basic build:

```bash
docker build -t mqttstuff:local .
```

Pass custom Python/Debian versions:

```bash
docker build \
  --build-arg python_version=3.12 \
  --build-arg debian_version=bookworm \
  -t mqttstuff:py312 .
```

Embed source metadata (useful in CI):

```bash
docker build \
  --build-arg gh_ref="${GITHUB_REF}" \
  --build-arg gh_sha="${GITHUB_SHA}" \
  --build-arg buildtime="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  -t mqttstuff:with-meta .
```

Multi-architecture build with buildx (example for amd64 and arm64):

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ghcr.io/youruser/mqttstuff:latest \
  --push .
```

Note: This repository already provides a `docker-config/` buildx context. You can reuse your existing builder or create a new one:

```bash
docker buildx create --name mbuilder --use || true
docker buildx inspect --bootstrap
```

### Running the image

The image uses `tini` as entrypoint and defaults to a no-op `tail -f /dev/null` command, so you can exec into it or run your own command.

Examples:

```bash
# Run interactively and inspect
docker run --rm -it \
  -e LOGURU_LEVEL=INFO \
  -e MQTTSTUFF_CONFIG_DIR_PATH=/app \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  mqttstuff:local bash

# Run a Python one-liner using the wrapper
docker run --rm -it mqttstuff:local \
  python -c "from mqttstuff.mosquittomqttwrapper import MQTTLastDataReader as R; print(R.get_most_recent_data_with_timeout('broker',1883,'user','pass','tele/+/STATE', retained='only'))"
```

### Why Docker here is useful

- Ensures consistent Python/dependency versions across dev machines and CI
- Provides a preconfigured environment for quick experiments against an MQTT broker
- Makes multi-arch builds straightforward with buildx

## Development

Helpful `Makefile` targets:

- `make install` – create venv and install dev requirements
- `make tests` – run pytest
- `make lint` – run Black
- `make isort` – fix import order
- `make tcheck` – run mypy on `scripts` and `mqttstuff`
- `make pypibuild` – build sdists/wheels with Hatch to `dist/`
- `make pypipush` – publish using Hatch (configure credentials first)

## Testing

Tests live under `tests/`. Run all tests with:

```bash
pytest -q
```

## License

This project is licensed under the LGPL where applicable/possible — see [LICENSE.md](LICENSE.md). Some files/parts may be governed by other licenses and/or licensors, such as [MIT](LICENSEMIT.md) | [GPL](LICENSEGPL.md) | [LGPL](LICENSELGPL.md). Please also check file headers/comments.

## Acknowledgments

See inline comments in the codebase for inspirations and references.

## ⚠️ Disclaimer

This is a development/experimental project. For production use, review security settings, customize configurations, and test thoroughly in your environment. Provided "as is" without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose and noninfringement. In no event shall the authors or copyright holders be liable for any claim, damages or other liability, whether in an action of contract, tort or otherwise, arising from, out of or in connection with the software or the use or other dealings in the software. Use at your own risk.