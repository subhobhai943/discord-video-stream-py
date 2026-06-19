"""SRTP-style packet encryption for Discord voice.

Supported modes:
  - aead_xchacha20_poly1305_rtpsize  (primary, PyNaCl)
  - xsalsa20_poly1305_lite_rtpsize   (legacy)
  - xsalsa20_poly1305_lite           (legacy)
  - xsalsa20_poly1305_suffix         (legacy)
  - xsalsa20_poly1305                (legacy)
  - aead_aes256_gcm_rtpsize          (newer, cryptography lib)

Reference: Discord voice docs + dank074/discord-video-stream
"""

from __future__ import annotations

import struct

from nacl.secret import SecretBox
from nacl.bindings import crypto_aead_xchacha20poly1305_ietf_encrypt


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def encrypt_packet(
    header: bytes,
    payload: bytes,
    secret_key: bytes,
    mode: str,
) -> bytes:
    """
    Encrypt *payload* using the negotiated *mode* and prepend *header*.

    Parameters
    ----------
    header:
        12-byte RTP header (already built by :mod:`.rtp`).
    payload:
        Raw codec bytes (Opus frame, H264 NAL fragment, etc.).
    secret_key:
        32-byte secret obtained from OP 4 Session Description.
    mode:
        Encryption mode string from the gateway negotiation.

    Returns
    -------
    bytes
        Complete encrypted RTP packet ready to send over UDP.
    """
    if mode in (
        "aead_xchacha20_poly1305_rtpsize",
        "aead_xchacha20_poly1305_poly1305_rtpsize",  # alias seen in the wild
    ):
        return _xchacha20_rtpsize(header, payload, secret_key)

    elif mode == "aead_aes256_gcm_rtpsize":
        return _aes256_gcm_rtpsize(header, payload, secret_key)

    elif mode in ("xsalsa20_poly1305_lite_rtpsize", "xsalsa20_poly1305_lite"):
        return _xsalsa20_lite(header, payload, secret_key, rtpsize=("rtpsize" in mode))

    elif mode == "xsalsa20_poly1305_suffix":
        return _xsalsa20_suffix(header, payload, secret_key)

    elif mode == "xsalsa20_poly1305":
        return _xsalsa20_normal(header, payload, secret_key)

    else:
        raise ValueError(f"Unsupported encryption mode: {mode!r}")


# ──────────────────────────────────────────────────────────────────────
# Mode implementations
# ──────────────────────────────────────────────────────────────────────

def _xchacha20_rtpsize(header: bytes, payload: bytes, key: bytes) -> bytes:
    """
    aead_xchacha20_poly1305_rtpsize:
      nonce = header (12 bytes) padded to 24 bytes with zeros
      additional_data = header
    """
    nonce = header + b"\x00" * 12  # 24-byte nonce
    encrypted = crypto_aead_xchacha20poly1305_ietf_encrypt(
        message=payload,
        aad=header,
        nonce=nonce,
        key=key,
    )
    return header + encrypted


def _aes256_gcm_rtpsize(header: bytes, payload: bytes, key: bytes) -> bytes:
    """
    aead_aes256_gcm_rtpsize:
      nonce = last 4 bytes of header, zero-padded to 12 bytes
      additional_data = header
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = b"\x00" * 8 + header[-4:]  # 12-byte nonce
    aesgcm = AESGCM(key)
    encrypted = aesgcm.encrypt(nonce, payload, header)
    return header + encrypted


def _xsalsa20_lite(
    header: bytes,
    payload: bytes,
    key: bytes,
    rtpsize: bool,
) -> bytes:
    """
    xsalsa20_poly1305_lite / xsalsa20_poly1305_lite_rtpsize:
      nonce = 4-byte little-endian counter appended to packet,
              zero-padded to 24 bytes for the box.
    """
    # Use the sequence number from the header as a simple nonce counter
    nonce_int = struct.unpack_from(">H", header, 2)[0]
    nonce = struct.pack("<I", nonce_int) + b"\x00" * 20
    box = SecretBox(key)
    encrypted = box.encrypt(payload, nonce=nonce).ciphertext
    nonce_suffix = struct.pack("<I", nonce_int)
    return header + encrypted + nonce_suffix


def _xsalsa20_suffix(header: bytes, payload: bytes, key: bytes) -> bytes:
    """
    xsalsa20_poly1305_suffix:
      nonce = 24 random bytes appended after the ciphertext.
    """
    import os
    nonce = os.urandom(24)
    box = SecretBox(key)
    encrypted = box.encrypt(payload, nonce=nonce).ciphertext
    return header + encrypted + nonce


def _xsalsa20_normal(header: bytes, payload: bytes, key: bytes) -> bytes:
    """
    xsalsa20_poly1305:
      nonce = 12-byte header zero-padded to 24 bytes.
    """
    nonce = header + b"\x00" * 12
    box = SecretBox(key)
    encrypted = box.encrypt(payload, nonce=nonce).ciphertext
    return header + encrypted
