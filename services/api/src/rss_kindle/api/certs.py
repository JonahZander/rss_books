from __future__ import annotations

import datetime as dt
import ipaddress
import logging
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

logger = logging.getLogger(__name__)


def ensure_self_signed(
    cert_path: Path,
    key_path: Path,
    san_ips: list[str] | None = None,
) -> None:
    """Generate a self-signed cert/key pair at the given paths if either is
    missing. Idempotent: existing files are left untouched so the cert is stable
    across restarts (it lives in the /data volume).

    The cert is only here so TLS-only clients (e.g. the Crosspoint e-reader) can
    connect at all — it is self-signed, so a verifying client must skip
    verification or trust it out of band. `san_ips` lets callers embed LAN IPs as
    SubjectAltName entries for clients that do check the hostname.
    """
    if cert_path.exists() and key_path.exists():
        return

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "rss-kindle-selector")])

    alt_names: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    for raw in san_ips or []:
        raw = raw.strip()
        if not raw:
            continue
        try:
            alt_names.append(x509.IPAddress(ipaddress.ip_address(raw)))
        except ValueError:
            # Not an IP literal — treat it as a DNS name instead.
            alt_names.append(x509.DNSName(raw))

    # Fixed, wide validity window backdated to 2020 — avoids clock-skew
    # rejections on devices with a wrong RTC, and we don't need precision.
    not_before = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    not_after = dt.datetime(2035, 1, 1, tzinfo=dt.UTC)

    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    logger.info("generated self-signed TLS cert at %s", cert_path)
