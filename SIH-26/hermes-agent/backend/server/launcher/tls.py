"""
TLS certificate generation for first-time setup.
Produces a self-signed cert if none exists. Logs clearly that it's self-signed.
No network calls — uses cryptography library only.
"""
from __future__ import annotations

import datetime
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def ensure_tls_cert(cert_path: Path, key_path: Path) -> None:
    if cert_path.exists() and key_path.exists():
        return

    log.warning(
        "No TLS certificate found. Generating a self-signed certificate at %s. "
        "For production, replace with a certificate signed by your internal CA "
        "(set TLS_CERT_PATH and TLS_KEY_PATH env vars).",
        cert_path,
    )

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        log.error("cryptography package not installed; cannot generate self-signed cert")
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "workbench.internal"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.DNSName("workbench.internal"),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    log.info("Self-signed TLS certificate written to %s", cert_path)
