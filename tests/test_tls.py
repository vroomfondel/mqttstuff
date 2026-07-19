import ssl

import pytest

from mqttstuff import MosquittoClientWrapper, MWTLSConfig
from mqttstuff.mosquittomqttwrapper import _build_paho_client, _resolve_tls_config

# --- Abnahmekriterien aus der Spec ---


def test_no_tls_leaves_ssl_context_unset() -> None:
    wrapper = MosquittoClientWrapper(host="localhost", port=1883, username="u", password="p")

    assert wrapper.client is not None
    assert wrapper.client._ssl_context is None
    assert wrapper.tls is None


def test_tls_true_sets_context_with_hostname_check() -> None:
    wrapper = MosquittoClientWrapper(host="localhost", port=8883, username="u", password="p", tls=True)

    assert wrapper.client is not None
    ctx = wrapper.client._ssl_context
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_tls_insecure_disables_hostname_and_chain_check() -> None:
    wrapper = MosquittoClientWrapper(
        host="localhost", port=8883, username="u", password="p", tls=True, tls_insecure=True
    )

    assert wrapper.client is not None
    ctx = wrapper.client._ssl_context
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.check_hostname is False
    assert ctx.verify_mode == ssl.CERT_NONE


def test_explicit_cert_reqs_wins_over_tls_insecure() -> None:
    client = _build_paho_client({}, "u", "p", MWTLSConfig(cert_reqs=ssl.CERT_REQUIRED, tls_insecure=True))

    ctx = client._ssl_context
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.check_hostname is False
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_certfile_without_keyfile_raises() -> None:
    with pytest.raises(ValueError):
        MosquittoClientWrapper(host="localhost", port=8883, tls=True, tls_certfile="/tmp/client.pem")


# --- Validierung der Parameter-Fassade ---


def test_keyfile_without_certfile_raises() -> None:
    with pytest.raises(ValueError):
        MosquittoClientWrapper(host="localhost", port=8883, tls=True, tls_keyfile="/tmp/client.key")


def test_tls_params_without_tls_enabled_raise() -> None:
    with pytest.raises(ValueError):
        MosquittoClientWrapper(host="localhost", port=1883, tls_ca_certs="/tmp/ca.pem")

    with pytest.raises(ValueError):
        MosquittoClientWrapper(host="localhost", port=1883, tls_insecure=True)


def test_model_combined_with_facade_params_raises() -> None:
    with pytest.raises(ValueError):
        MosquittoClientWrapper(host="localhost", port=8883, tls=MWTLSConfig(), tls_insecure=True)


def test_resolve_tls_config_passthrough_and_disable() -> None:
    cfg = MWTLSConfig(ca_certs="/tmp/ca.pem")
    assert _resolve_tls_config(cfg) is cfg
    assert _resolve_tls_config(False) is None

    built = _resolve_tls_config(True, tls_ca_certs="/tmp/ca.pem", tls_insecure=True)
    assert built is not None
    assert built.ca_certs == "/tmp/ca.pem"
    assert built.tls_insecure is True


# --- MWTLSConfig-Modell ---


def test_mwtlsconfig_defaults() -> None:
    cfg = MWTLSConfig()

    assert cfg.ca_certs is None
    assert cfg.certfile is None
    assert cfg.keyfile is None
    assert cfg.keyfile_password is None
    assert cfg.cert_reqs is None
    assert cfg.tls_version is None
    assert cfg.ciphers is None
    assert cfg.alpn_protocols is None
    assert cfg.tls_insecure is False


def test_mwtlsconfig_cert_key_pair_validation() -> None:
    with pytest.raises(ValueError):
        MWTLSConfig(certfile="/tmp/client.pem")

    with pytest.raises(ValueError):
        MWTLSConfig(keyfile="/tmp/client.key")


def test_wrapper_accepts_mwtlsconfig_model() -> None:
    wrapper = MosquittoClientWrapper(
        host="localhost", port=8883, username="u", password="p", tls=MWTLSConfig(tls_insecure=True)
    )

    assert wrapper.client is not None
    ctx = wrapper.client._ssl_context
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.check_hostname is False
    assert ctx.verify_mode == ssl.CERT_NONE


# --- gemeinsame Client-Factory (wird auch vom MQTTLastDataReader genutzt) ---


def test_build_paho_client_without_tls() -> None:
    client = _build_paho_client({}, "u", "p", None)
    assert client._ssl_context is None


def test_build_paho_client_with_tls() -> None:
    client = _build_paho_client({}, "u", "p", MWTLSConfig())
    ctx = client._ssl_context
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.check_hostname is True
