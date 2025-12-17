![mypy and pytests](https://github.com/vroomfondel/mqttstuff/actions/workflows/mypynpytests.yml/badge.svg)
![Cumulative Clones](https://img.shields.io/endpoint?logo=github&url=https://gist.githubusercontent.com/vroomfondel/8a315c36125952c9976548dfbf45cb7b/raw/mqttstuff_clone_count.json)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/mqttstuff?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=PyPi+Downloads)](https://pepy.tech/projects/mqttstuff)

[![https://github.com/vroomfondel/mqttstuff/raw/main/Gemini_Generated_Image_mqttstuff_i3269fi3269fi326_250x250.png](https://github.com/vroomfondel/mqttstuff/raw/main/Gemini_Generated_Image_mqttstuff_i3269fi3269fi326_250x250.png)](https://github.com/vroomfondel/mqttstuff)

# MQTTStuff

Lightweight helper utilities for working with MQTT via Paho, with convenient wrappers for:

- Connecting and subscribing to topics, including retained-message handling
- Publishing one or many messages with consistent metadata and timestamps
- Reading “last/most recent” messages with timeout-based collection and optional type conversion
- Developer helpers for JSON pretty-printing, deep updates, and logging configuration

- Repository: https://github.com/vroomfondel/mqttstuff
- Package: `mqttstuff`

## Overview

MQTTStuff provides a higher-level interface over `paho-mqtt` to simplify common patterns:

- A `MosquittoClientWrapper` to configure, connect, subscribe, and publish with minimal boilerplate
- A `MQTTLastDataReader` utility to retrieve the most recent messages for one or more topics quickly
- A `MWMqttMessage` normalization data format for sending/receiving data (optional metadata) from/to IOT devices/sensors

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
from mqttstuff import MosquittoClientWrapper

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
from mqttstuff import MQTTLastDataReader

data = MQTTLastDataReader.get_most_recent_data_with_timeout(
    host="localhost", port=1883, username="user", password="pass",
    topics=["tele/+/STATE", "stat/+/STATUS"],
    retained="only",  # "yes" | "no" | "only"
    rettype="str_raw", # or "json", "valuemsg", "str", "int", "float"
)
print(data)
```

## Notes on configuration

This repository does not provide a central `config.py` anymore. Pass your MQTT connection settings directly to the wrapper (see examples above) or manage configuration in your own application code.

## Python Modules

Each Python module provided by this repository is documented here with a focused explanation of its purpose and usage.

### Package: `mqttstuff`

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
from mqttstuff import MosquittoClientWrapper

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

<!-- The former `mqttcommander` and `config` modules have been removed from this repository. -->

### Module: `Helper`

Small utilities used across the project:

- `ComplexEncoder` for JSON serialization of complex types (UUID, datetimes, dict/list pretty rendering)
- `print_pretty_dict_json`, `get_pretty_dict_json`, `get_pretty_dict_json_no_sort`
- `update_deep(base, u)` for deep dict/list merge/update
- `get_exception_tb_as_string(exc)` for converting exception tracebacks to strings
- `get_loguru_logger_info()` to introspect Loguru handlers and filters

## Docker

Docker image building and publishing have been removed from this repository. If you need containerization, consider creating a separate Docker setup in your own project using this package from PyPI.

## Development

Helpful `Makefile` targets:

- `make help` – list available targets with short descriptions
- `make install` – create virtualenv and install development requirements
- `make venv` – ensure `.venv` exists and dev requirements are installed
- `make tests` – run pytest
- `make lint` – run Black code formatter
- `make isort` – fix and check import order
- `make tcheck` – run mypy type checks over `*.py`, `scripts/`, and `mqttstuff/`
- `make commit-checks` – run pre-commit hooks on all files
- `make prepare` – run tests and commit-checks (useful before committing/PRs)
- `make pypibuild` – build sdist and wheel with Hatch into `dist/`
- `make pypipush` – publish built artifacts with Hatch (configure credentials first)

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