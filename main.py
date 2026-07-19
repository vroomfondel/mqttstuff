import datetime
import os
from typing import Dict, Optional

import mqttstuff

mqttstuff.configure_loguru_default_with_skiplog_filter()

from loguru import logger

logger.enable("mqttstuff")


def _main(
    host: str,
    port: int,
    username: str,
    password: str,
    topic: str = "mqttstuff/TEST",
    metadata: Optional[Dict] = None,
    tls: bool = False,
    tls_ca_certs: Optional[str] = None,
    tls_certfile: Optional[str] = None,
    tls_keyfile: Optional[str] = None,
    tls_insecure: bool = False,
) -> None:
    mqttclient: mqttstuff.MosquittoClientWrapper = mqttstuff.MosquittoClientWrapper(
        host=host,
        port=port,
        username=username,
        password=password,
        tls=tls,
        tls_ca_certs=tls_ca_certs,
        tls_certfile=tls_certfile,
        tls_keyfile=tls_keyfile,
        tls_insecure=tls_insecure,
    )

    connected: bool = mqttclient.wait_for_connect_and_start_loop()
    logger.debug(f"mqttclient.is_connected()={mqttclient.is_connected()} {connected=}")
    # mqttclient.connect_and_start_loop_forever()

    mqttclient.publish_one(
        topic="somestuff/mqttstuff/TEST",
        value=779,
        created_at=datetime.datetime.now(tz=mqttstuff._tz_berlin),
        metadata=metadata,  # type: ignore
    )

    mqttclient.disconnect()


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="MQTT Client")
    parser.add_argument("--host", type=str, required=True, help="MQTT broker host")
    parser.add_argument("--port", type=int, required=True, help="MQTT broker port")
    parser.add_argument("--username", type=str, required=True, help="MQTT username")
    parser.add_argument("--password", type=str, required=True, help="MQTT password")
    parser.add_argument("--topic", type=str, default="mqttstuff/TEST", help="MQTT topic (default: mqttstuff/TEST)")
    parser.add_argument("--metadata", type=str, default=None, help="Metadata as JSON string")
    parser.add_argument(
        "--tls", action="store_true", help="Enable TLS (broker TLS port, typically 8883, must be given via --port)"
    )
    parser.add_argument(
        "--tls-ca-certs", type=str, default=None, help="Path to PEM CA bundle (default: system CA store)"
    )
    parser.add_argument(
        "--tls-certfile", type=str, default=None, help="Client certificate for mTLS (requires --tls-keyfile)"
    )
    parser.add_argument("--tls-keyfile", type=str, default=None, help="Private key for --tls-certfile")
    parser.add_argument(
        "--tls-insecure",
        action="store_true",
        help="Skip certificate verification entirely: no hostname check, no chain validation (dev only)",
    )

    args = parser.parse_args()

    metadata = None
    if args.metadata:
        metadata = json.loads(args.metadata)

    _main(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        topic=args.topic,
        metadata=metadata,
        tls=args.tls,
        tls_ca_certs=args.tls_ca_certs,
        tls_certfile=args.tls_certfile,
        tls_keyfile=args.tls_keyfile,
        tls_insecure=args.tls_insecure,
    )
