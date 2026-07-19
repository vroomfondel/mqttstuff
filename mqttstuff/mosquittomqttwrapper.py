import datetime
import functools
import json
import pprint
import ssl
import threading
import time
from json import JSONDecodeError
from threading import Condition
from typing import Any, Callable, ClassVar, Dict, List, Literal, Optional, Tuple, Union

import pytz
from paho.mqtt.client import Client, MQTTMessage, MQTTMessageInfo, MQTTv311
from paho.mqtt.enums import CallbackAPIVersion
from pydantic import BaseModel, model_validator

_tz_berlin: datetime.tzinfo = pytz.timezone("Europe/Berlin")

from loguru import logger

# moved to __init__.py
# logger.disable(__name__)

logger.debug(f"{__name__} DEBUG")
logger.info(f"{__name__} INFO")

# Tuple[
#                 str,
#                 Union[int, float, str, dict],
#                 Optional[datetime.datetime],
#                 Optional[Dict],
#             ]


class MWMqttMessage(BaseModel):
    topic: str
    value: Optional[Union[float, str, Dict[Any, Any]]] = None
    valuedt: Optional[datetime.datetime] = None
    retained: bool = False
    qos: int = 0  # setting default here to something more robust than qos=0 ?!
    metadata: Optional[Dict[str, Any]] = None
    rettype: Literal["json", "str", "int", "float", "valuemsg", "str_raw"] = "valuemsg"

    @classmethod
    def from_pahomsg(
        cls,
        pahomsg: MQTTMessage,
        rettype: Literal["json", "str", "int", "float", "valuemsg", "str_raw"] = "valuemsg",
        created_at_fieldname: str = "created_at",
    ) -> "MWMqttMessage":
        value: Optional[Union[float, str, dict[Any, Any]]] = None
        valuedt: Optional[datetime.datetime] = None

        qos: int = pahomsg.qos
        payload: bytes = pahomsg.payload  # type: ignore[attr-defined]

        if rettype == "json" or rettype == "valuemsg":
            d: Dict = json.loads(payload.decode("utf-8"))

            if rettype == "valuemsg":
                value = d["value"]
                valuedt = datetime.datetime.fromisoformat(d[created_at_fieldname]).astimezone(_tz_berlin)
            else:
                value = d
        elif rettype == "str_raw":
            value = payload.decode("utf-8")
        elif rettype == "str":
            value = payload.decode("utf-8")
            if value[0] == "{":
                # logger.debug("OUTODETECT JSON")
                value = json.loads(value)
        elif rettype == "int":
            value = int(payload.decode("utf-8"))
        elif rettype == "float":
            value = float(payload.decode("utf-8"))

        return MWMqttMessage(
            topic=pahomsg.topic, value=value, valuedt=valuedt, retained=pahomsg.retain, rettype=rettype, qos=qos
        )


class MWTLSConfig(BaseModel):
    """TLS/SSL configuration for the MQTT connection.

    All fields default to ``None``/``False``; unset fields are passed through to
    :meth:`paho.mqtt.client.Client.tls_set`, which then applies its own secure
    defaults (system CA store, ``ssl.CERT_REQUIRED``, ``ssl.PROTOCOL_TLS_CLIENT``).

    Note:
        Enabling TLS does not change the port — MQTT-over-TLS brokers typically
        listen on 8883, which must be passed explicitly by the caller.

    Attributes:
        ca_certs: Path to a PEM-encoded CA bundle. ``None`` uses the system CA store.
        certfile: Path to a PEM-encoded client certificate (mTLS). Requires ``keyfile``.
        keyfile: Path to the client certificate's private key. Requires ``certfile``.
        keyfile_password: Password for an encrypted ``keyfile``.
        cert_reqs: Server certificate verification mode; paho defaults to
            ``ssl.CERT_REQUIRED`` when unset. Setting this explicitly wins over
            ``tls_insecure`` (which otherwise implies ``ssl.CERT_NONE``), so
            ``cert_reqs=ssl.CERT_REQUIRED`` + ``tls_insecure=True`` still
            validates the chain while skipping only the hostname check.
        tls_version: TLS protocol version constant (e.g. ``ssl.PROTOCOL_TLS_CLIENT``);
            paho picks a secure default when unset.
        ciphers: OpenSSL cipher string; ``None`` uses the defaults.
        alpn_protocols: ALPN protocols to announce (e.g. for AWS IoT on port 443).
        tls_insecure: Skip server certificate verification entirely — no hostname
            check and no chain/CA validation (implies ``cert_reqs=ssl.CERT_NONE``
            unless ``cert_reqs`` is set explicitly). This accepts self-signed,
            expired and unknown-CA certificates, e.g. a reverse proxy serving its
            default throwaway certificate. The connection stays encrypted but
            becomes MITM-able — development/testing only.
    """

    ca_certs: Optional[str] = None
    certfile: Optional[str] = None
    keyfile: Optional[str] = None
    keyfile_password: Optional[str] = None
    cert_reqs: Optional[ssl.VerifyMode] = None
    tls_version: Optional[int] = None
    ciphers: Optional[str] = None
    alpn_protocols: Optional[List[str]] = None
    tls_insecure: bool = False

    @model_validator(mode="after")
    def _check_cert_key_pair(self) -> "MWTLSConfig":
        if (self.certfile is None) != (self.keyfile is None):
            raise ValueError("certfile and keyfile must be provided together (mTLS needs both)")
        return self


def _resolve_tls_config(
    tls: Union[bool, MWTLSConfig],
    tls_ca_certs: Optional[str] = None,
    tls_certfile: Optional[str] = None,
    tls_keyfile: Optional[str] = None,
    tls_insecure: bool = False,
) -> Optional[MWTLSConfig]:
    """Normalize the TLS parameter facade into a single :class:`MWTLSConfig`.

    Args:
        tls: ``False`` disables TLS, ``True`` enables it (configured via the
            ``tls_*`` parameters), or a ready-made :class:`MWTLSConfig`.
        tls_ca_certs: Path to a PEM CA bundle; ``None`` uses the system CA store.
        tls_certfile: Client certificate for mTLS.
        tls_keyfile: Private key belonging to ``tls_certfile``.
        tls_insecure: Skip certificate verification entirely — no hostname check
            and no chain validation (development only).

    Returns:
        Optional[MWTLSConfig]: The effective TLS configuration, or ``None`` if
        TLS is disabled.

    Raises:
        ValueError: If ``tls_*`` parameters are combined with a
            :class:`MWTLSConfig` instance, or given while ``tls`` is ``False``,
            or if ``tls_certfile``/``tls_keyfile`` are not passed together.
    """
    facade_used: bool = tls_ca_certs is not None or tls_certfile is not None or tls_keyfile is not None or tls_insecure

    if isinstance(tls, MWTLSConfig):
        if facade_used:
            raise ValueError("pass TLS options either as a MWTLSConfig via 'tls' OR via the tls_* parameters, not both")
        return tls

    if not tls:
        if facade_used:
            raise ValueError("tls_* parameters were given, but TLS is not enabled (tls=False)")
        return None

    return MWTLSConfig(ca_certs=tls_ca_certs, certfile=tls_certfile, keyfile=tls_keyfile, tls_insecure=tls_insecure)


def _build_paho_client(
    callback_userdata: Dict[str, Any],
    username: Optional[str],
    password: Optional[str],
    tls: Optional[MWTLSConfig] = None,
) -> Client:
    """Create and configure a paho :class:`~paho.mqtt.client.Client`.

    Shared factory for :class:`MosquittoClientWrapper` and
    :class:`MQTTLastDataReader`. Each call returns a fresh client instance, so
    ``tls_set()`` runs at most once per client (paho raises on a second call).

    Args:
        callback_userdata: Userdata dict passed to the paho client.
        username: MQTT username.
        password: MQTT password.
        tls: TLS configuration; ``None`` keeps the connection plaintext.

    Returns:
        Client: The configured (not yet connected) paho client.
    """
    client: Client = Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id="",
        clean_session=True,
        userdata=callback_userdata,
        protocol=MQTTv311,
        transport="tcp",
        reconnect_on_failure=True,
        manual_ack=False,
    )

    if tls is not None:
        # tls_insecure means "skip verification", not just "skip the hostname check":
        # without CERT_NONE the chain is still validated and self-signed / unknown-CA
        # certificates (e.g. a reverse proxy's default certificate) keep failing.
        # An explicit cert_reqs always wins, so chain-only verification stays possible.
        cert_reqs: Optional[ssl.VerifyMode] = tls.cert_reqs
        if tls.tls_insecure and cert_reqs is None:
            cert_reqs = ssl.CERT_NONE

        client.tls_set(
            ca_certs=tls.ca_certs,
            certfile=tls.certfile,
            keyfile=tls.keyfile,
            cert_reqs=cert_reqs,
            tls_version=tls.tls_version,
            ciphers=tls.ciphers,
            keyfile_password=tls.keyfile_password,
            alpn_protocols=tls.alpn_protocols,
        )
        if tls.tls_insecure:
            logger.warning(
                "TLS certificate verification disabled (tls_insecure=True, cert_reqs={}): "
                "connection is encrypted but MITM-able — do not use in production",
                cert_reqs,
            )
            client.tls_insecure_set(True)

    client.username_pw_set(username, password)

    return client


class MosquittoClientWrapper:
    logger = logger.bind(classname=__qualname__)

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        topics: Optional[List[str]] = None,
        timeout_connect_seconds: Optional[int] = None,
        *,
        tls: Union[bool, MWTLSConfig] = False,
        tls_ca_certs: Optional[str] = None,
        tls_certfile: Optional[str] = None,
        tls_keyfile: Optional[str] = None,
        tls_insecure: bool = False,
    ) -> None:
        """Initialize the wrapper and set up the underlying paho client.

        Args:
            host: MQTT broker host.
            port: MQTT broker port. Note: enabling TLS does not switch the port
                automatically — pass the broker's TLS port (typically 8883) yourself.
            username: MQTT username.
            password: MQTT password.
            topics: Topics to subscribe to on connect.
            timeout_connect_seconds: Timeout for waiting on the initial connect.
            tls: ``False`` (default) disables TLS, ``True`` enables it configured
                via the ``tls_*`` parameters, or pass a :class:`MWTLSConfig` for
                full control (ciphers, ALPN, cert_reqs, ...).
            tls_ca_certs: Path to a PEM CA bundle; ``None`` uses the system CA store.
            tls_certfile: Client certificate for mTLS (requires ``tls_keyfile``).
            tls_keyfile: Private key for ``tls_certfile``.
            tls_insecure: Skip server certificate verification entirely — neither
                hostname nor chain/CA is checked, so self-signed, expired and
                unknown-CA certificates are accepted. The connection stays
                encrypted but is MITM-able. Development/testing only.

        Raises:
            ValueError: On inconsistent TLS parameters (``tls_*`` given while
                ``tls=False``, ``tls_*`` combined with a :class:`MWTLSConfig`,
                or certfile/keyfile not passed together).
        """
        self.timeout_connect_seconds: Optional[int] = timeout_connect_seconds
        self.topics: Optional[List[str]] = topics
        self.client: Optional[Client] = None
        self.noisy_connect: bool = False
        self.noisy_client: bool = False
        # self.subscriptions: Optional[list[str]] = None
        self.callback_userdata: Dict[str, Any] = {}

        self.host: Optional[str] = host
        self.port: Optional[int] = port
        self.username: Optional[str] = username
        self.password: Optional[str] = password

        self.tls: Optional[MWTLSConfig] = _resolve_tls_config(
            tls, tls_ca_certs, tls_certfile, tls_keyfile, tls_insecure
        )

        self._setup_mqtt_client()

    def on_connect(self, client: Client, userdata: Any, flags: Any, rc: Any, props: Any) -> None:
        if self.noisy_connect:
            self.logger.debug(f"{threading.get_ident()=} {client=} {userdata=} {flags=} {rc=} {props=}")

        if "topics" in userdata and userdata["topics"]:
            if isinstance(userdata["topics"], list):
                sublist: List[Tuple[str, int]] = []
                for topic in userdata["topics"]:
                    # client.subscribe(topic, userdata["qos"])
                    sublist.append((topic, userdata["qos"]))

                if self.noisy_connect:
                    self.logger.debug(f"subscribing to multi_topic: {sublist=}")
                client.subscribe(sublist)
            else:
                if self.noisy_connect:
                    self.logger.debug(f'subscribing to SINGLE topic: {userdata["topics"]=} {userdata["qos"]=}')
                client.subscribe(userdata["topics"], userdata["qos"])

        if "cond_connected" in userdata and isinstance(userdata["cond_connected"], threading.Condition):
            cond_connected: threading.Condition = userdata["cond_connected"]
            with cond_connected:
                cond_connected.notify_all()

    def set_topics(self, topics: List[str]) -> None:
        # should be synchronized/(re-)entry-locked

        oldtopics: Optional[List[str]] = self.topics

        self.topics = topics
        self.callback_userdata["topics"] = self.topics

        if not self.client or not self.client.is_connected():
            return

        to_subscribe_add: List[Tuple[str, int]] = []
        myqos: int = self.callback_userdata["qos"]

        if not oldtopics:
            self.topics = topics
            self.callback_userdata["topics"] = self.topics

            # to_subscribe = [(oldt, myqos) for oldt in oldtopics]
        else:
            for oldtopic in oldtopics:
                if not oldtopic in topics:
                    self.logger.debug(f"Unsubscribing from {oldtopic=}")
                    self.client.unsubscribe(oldtopic)

            for newtopic in topics:
                if not newtopic in oldtopics:
                    to_subscribe_add.append((newtopic, myqos))

        if len(to_subscribe_add) > 0:
            self.client.subscribe(to_subscribe_add)

    def _setup_mqtt_client(self) -> None:
        """(Re-)create the underlying paho client.

        Builds a fresh :class:`~paho.mqtt.client.Client` on every call (via
        :func:`_build_paho_client`), so TLS setup runs exactly once per client
        instance even if this method is called multiple times.
        """
        self.callback_userdata = {"cond_connected": threading.Condition(), "topics": self.topics, "qos": 1}

        self.client = _build_paho_client(self.callback_userdata, self.username, self.password, self.tls)

        if self.noisy_client:
            self.client.enable_logger()

        self.client.on_connect = self.on_connect
        # functools.partial(
        #     self.on_connect, self
        # )  # wg. (re-)subscribe zu den topics

        # client.message_callback_add("husqvarna/automower/pongs", on_pong_message)
        # client.on_message = lambda _client, _usd, _msg: self.logger.debug(
        #     f"{threading.get_ident()=} {_msg.topic=} {_msg.payload=}"
        # )

    def _on_msg_callback_wrapper(
        self,
        client: Client,
        userdata: Any,
        msg: MQTTMessage,
        realtargetfunc: Callable,
        rettype: Literal["json", "str", "int", "float", "valuemsg", "str_raw"] = "valuemsg",
    ) -> None:
        if client._thread:
            self.logger.debug(f"{client._thread.name=}")

        valuemsg: MWMqttMessage = MWMqttMessage.from_pahomsg(msg, rettype)
        realtargetfunc(valuemsg, userdata)

    def add_message_callback(
        self,
        sub: str,
        callback: Callable,
        rettype: Literal["json", "str", "int", "float", "valuemsg"] = "valuemsg",
    ) -> None:
        assert self.client is not None

        self.client.message_callback_add(
            sub,
            functools.partial(self._on_msg_callback_wrapper, realtargetfunc=callback, rettype=rettype),
        )

    def remove_message_callback(self, sub: str) -> None:
        assert self.client is not None
        self.client.message_callback_remove(sub)

    def set_on_msg_callback(
        self, callback: Callable, rettype: Literal["json", "str", "int", "float", "valuemsg", "str_raw"] = "valuemsg"
    ) -> None:
        assert self.client is not None
        self.client.on_message = functools.partial(
            self._on_msg_callback_wrapper, realtargetfunc=callback, rettype=rettype
        )

    def is_connected(self) -> bool:
        if not self.client:
            return False

        return self.client.is_connected()

    def wait_for_connect_and_start_loop(self) -> bool:
        assert self.client is not None
        assert self.host and self.port

        if self.noisy_connect:
            self.logger.debug(f"{threading.current_thread().name=}")

        connected: bool = False

        with self.callback_userdata["cond_connected"]:
            self.client.connect(self.host, self.port, 60)
            self.client.loop_start()

            if self.noisy_connect:
                self.logger.debug("WAITING FOR CONNECTED COND...")

            # callback_userdata["cond_connected"].wait_for(client.is_connected)
            connected = self.callback_userdata["cond_connected"].wait_for(
                timeout=self.timeout_connect_seconds,
                predicate=lambda: self.client.is_connected(),
            )
            if self.noisy_connect:
                self.logger.debug(f"AFTER wait for CONNECTED::{connected=}")

        return connected

    def connect_and_start_loop_forever(
        self,
        topics: Optional[List[str]] = None,
        timeout_connect_seconds: Optional[int] = None,
    ) -> None:
        assert self.client is not None
        assert self.host and self.port

        self.timeout_connect_seconds = timeout_connect_seconds

        if topics:
            self.set_topics(topics)

        # cond: Condition = self.callback_userdata["cond_connected"]

        if timeout_connect_seconds:
            self.client.connect(self.host, self.port, 60)

            # time.sleep(2)
            connected: bool = False
            starttime = time.time()
            i: int = 0
            while starttime + timeout_connect_seconds > time.time():
                if self.noisy_connect:
                    self.logger.debug(f"LOOP:#{i}")
                    i += 1

                if self.client.is_connected():
                    connected = True
                    break

                self.client.loop()

            self.logger.debug(f"CONNECTED: {connected=}")

        else:
            self.client.connect(self.host, self.port, 60)

        self.logger.debug("STARTING FOREVER-LOOP")
        self.client.loop_forever()

    def publish_multiple(self, msgs: List[MWMqttMessage], timeout: Optional[int] = None) -> List[bool]:
        # msgs_to_send: List[Dict] = []
        assert self.client is not None

        ret: List[bool] = []

        for msg in msgs:
            rettype: Literal["json", "str", "int", "float", "valuemsg", "str_raw"] = msg.rettype
            retain: bool = msg.retained
            qos: int = msg.qos

            metadata_me: Optional[Dict] = None

            if msg.metadata:
                metadata_me = msg.metadata.copy()

            if msg.valuedt is not None and metadata_me is not None:
                metadata_me["created_at"] = msg.valuedt.isoformat(timespec="milliseconds")
                # self.logger.debug(f"setting created_at to: {metadata_me['created_at']}")

            payload_data: dict = {
                "value": msg.value,
            }
            if metadata_me:
                payload_data.update(**metadata_me)

            payload: Union[float, str, dict[Any, Any]] | None = None
            # TODO HT 20240916 proper check for direct dict/json-msg.value
            if msg.value is not None:
                if rettype == "valuemsg" or rettype == "json":
                    payload = json.dumps(payload_data, default=str) if metadata_me else msg.value
                else:
                    payload = msg.value

            if self.noisy_client:
                self.logger.debug("BEFORE PUBLISH")

            if isinstance(payload, dict):
                payload = json.dumps(payload, default=str)

            msginfo: MQTTMessageInfo = self.client.publish(
                topic=msg.topic,
                # payload=json.dumps(payload_data, default=str),
                payload=payload,
                retain=retain,
                qos=qos,
            )

            # self.logger.debug("AFTER PUBLISH")
            try:
                msginfo.wait_for_publish(timeout=timeout)
                ret.append(True)
            except Exception as ex:
                self.logger.opt(exception=ex).error(ex)
                ret.append(False)

            # self.logger.debug("AFTER WAIT FOR PUBLISH")

        return ret

    def disconnect(self) -> None:
        assert self.client is not None
        self.client.disconnect()

    def publish_one(
        self,
        topic: str,
        value: Union[int, float, str, dict] | None,
        created_at: Optional[datetime.datetime] = None,
        metadata: Optional[dict] = None,
        rettype: Literal["json", "str", "int", "float", "valuemsg"] = "valuemsg",
        retain: bool = False,
        timeout: Optional[int] = None,
    ) -> bool:

        msg: MWMqttMessage = MWMqttMessage(
            topic=topic, value=value, valuedt=created_at, metadata=metadata, rettype=rettype, retained=retain
        )
        return self.publish_multiple(msgs=[msg], timeout=timeout)[0]


# msg = {‘topic’:”<topic>”, ‘payload’:”<payload>”, ‘qos’:<qos>, ‘retain’:<retain>}


class MQTTLastDataReader:
    logger: ClassVar = logger.bind(classname=__qualname__)

    @classmethod
    def get_most_recent_data_with_timeout(
        cls,
        host: str,
        port: int,
        username: str,
        password: str,
        topics: Union[str, List[str]],
        noisy: bool = False,
        timeout_msgreceived_seconds: Optional[float] = 20,
        retained: Literal["yes", "no", "only"] = "no",
        timeout_connect_seconds: Optional[float] = 20,
        max_received_msgs: int = 1,
        rettype: Literal["json", "str", "int", "float", "valuemsg", "str_raw"] = "str_raw",
        fallback_rettype: Literal["json", "str", "int", "float", "valuemsg", "str_raw"] = "str_raw",
        created_at_fieldname: str = "created_at",
        *,
        tls: Union[bool, MWTLSConfig] = False,
        tls_ca_certs: Optional[str] = None,
        tls_certfile: Optional[str] = None,
        tls_keyfile: Optional[str] = None,
        tls_insecure: bool = False,
    ) -> Optional[list[MWMqttMessage]]:
        if noisy:
            cls.logger.debug(
                f"GETMOSTRECENTDATA_WITH_TIMEOUT::{topics=} {timeout_msgreceived_seconds=} {timeout_connect_seconds=} {retained=}"
            )

        def on_connect(client: Client, userdata: Any, flags: Any, rc: Any, props: Any) -> None:
            if noisy:
                cls.logger.debug(f"{client=} {userdata=} {flags=} {rc=} {props=}")

            if isinstance(userdata["topics"], list):
                sublist: List[Tuple[str, int]] = []
                for topic in userdata["topics"]:
                    # client.subscribe(topic, userdata["qos"])
                    sublist.append((topic, userdata["qos"]))

                if noisy:
                    cls.logger.debug(f"subscribing to multi_topic: {sublist=}")
                client.subscribe(sublist)
            else:
                if noisy:
                    cls.logger.debug(f'subscribing to SINGLE topic: {userdata["topics"]=} {userdata["qos"]=}')
                client.subscribe(userdata["topics"], userdata["qos"])

            if "cond_connected" in userdata and isinstance(userdata["cond_connected"], Condition):
                cond_connected: Condition = userdata["cond_connected"]
                with cond_connected:
                    cond_connected.notify_all()

        def on_msg(mqttclient: Client, userdata: Dict[str, Any], msg: MQTTMessage) -> None:
            # self.logger.debug(f"{client=} {userdata=} {msg=} {msg.topic=} {msg.retain=} {msg.timestamp=} {msg.payload=}")

            if noisy:
                cls.logger.debug(f"{msg.topic=} {msg.retain=} {msg.timestamp=} {msg.mid=} {msg.payload=}")

            if msg.retain:
                if userdata["retained"] == "no":
                    return
            elif userdata["retained"] == "only":
                return

            received_msgs: list[MWMqttMessage]
            if "msgs_received" in userdata:
                received_msgs = userdata["msgs_received"]
            else:
                received_msgs = []
                userdata["msgs_received"] = received_msgs

            if max_received_msgs == -1 or len(received_msgs) < max_received_msgs:
                try:
                    received_msgs.append(
                        MWMqttMessage.from_pahomsg(msg, rettype, created_at_fieldname=created_at_fieldname)
                    )
                except JSONDecodeError as e:  # TODO should also check for other decode orrors than JSONDecodeError
                    logger.error(f"CAUGHT JSON-decoding error: {e}")
                    received_msgs.append(
                        MWMqttMessage.from_pahomsg(msg, fallback_rettype, created_at_fieldname=created_at_fieldname)
                    )
                    # if noisy:
                    #     cls.logger.debug(f"Caught JSONDecodeError -> switch to str_raw override for value {msg.payload=}")
                    # logger.opt(exception=e).error(e)

            # userdata["received_a_msg"] = time.time()
            if "cond_msg" in userdata and isinstance(userdata["cond_msg"], Condition):
                cond_msg: Condition = userdata["cond_msg"]
                with cond_msg:
                    cond_msg.notify_all()

        callback_userdata: Dict[str, Any] = {
            "topics": topics,
            "qos": 1,
            "retained": retained,
            "cond_connected": Condition(),
            "cond_msg": Condition(),
        }

        tls_config: Optional[MWTLSConfig] = _resolve_tls_config(
            tls, tls_ca_certs, tls_certfile, tls_keyfile, tls_insecure
        )

        client: Client = _build_paho_client(callback_userdata, username, password, tls_config)

        if noisy:
            client.enable_logger()

        client.on_connect = on_connect
        client.on_message = on_msg

        connected: bool = False
        with callback_userdata["cond_connected"]:
            client.connect(host, port, 60)
            client.loop_start()

            if noisy:
                cls.logger.debug("WAITING FOR CONNECTED COND...")
            # callback_userdata["cond_connected"].wait_for(client.is_connected)
            connected = callback_userdata["cond_connected"].wait_for(
                timeout=timeout_connect_seconds, predicate=lambda: client.is_connected()
            )
            if noisy:
                cls.logger.debug(f"AFTER wait for CONNECTED::{connected=}")

        if not connected:
            return None

        had_one_msg_received: bool = False

        with callback_userdata["cond_msg"]:
            while True:
                if noisy:
                    cls.logger.debug("WAITING FOR MSG RECEIVED COND...")

                # had_one_msg_received = callback_userdata["cond_msg"].wait_for(
                #     timeout=timeout_msgreceived_seconds,
                #     predicate=lambda: "received_a_msg" in callback_userdata,
                # )
                my_msg_received: bool = callback_userdata["cond_msg"].wait(timeout=timeout_msgreceived_seconds)
                had_one_msg_received = had_one_msg_received or my_msg_received
                if noisy:
                    cls.logger.debug(f"AFTER wait for MSG_RECEIVED::{callback_userdata["msgs_received"][-1]=}")

                # cleanup for next
                # del callback_userdata["received_a_msg"]

                if not my_msg_received:
                    break

                if 1 <= max_received_msgs <= len(callback_userdata["msgs_received"]):
                    break

        client.disconnect()

        if had_one_msg_received:
            msg: MWMqttMessage

            if noisy:
                for msg in callback_userdata["msgs_received"]:
                    cls.logger.debug(f"MSG_RECEIVED::\n{pprint.pformat(msg.model_dump(), indent=4, sort_dicts=True)}")
                    cls.logger.debug(f"{msg.topic=} {msg.retained=} {msg.value=}")

            msgs = callback_userdata["msgs_received"]

            if isinstance(msgs, list) and len(msgs) == 0:
                return None

            return msgs

        return None
