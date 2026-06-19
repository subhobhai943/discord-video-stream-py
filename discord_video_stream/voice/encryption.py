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
from functools import lru_cache

from nacl.secret import SecretBox
from nacl.bindings import crypto_aead_xchacha20poly1305_ietf_encrypt

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS_AES_GCM = True
except ImportError:  # pragma: no cover
    _HAS_AES_GCM = False


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def encrypt_packet(
    header: bytes,
    payload: bytes,
    secret_key: bytes,
    mode: str,
    nonce_counter: int = 0,
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
    nonce_counter:
        Monotonically incrementing 32-bit counter used as the nonce for
        ``_lite`` and ``aes256_gcm`` modes.  Must be tracked externally
        and incremented after each call.

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
        return _aes256_gcm_rtpsize(header, payload, secret_key, nonce_counter)

    elif mode in ("xsalsa20_poly1305_lite_rtpsize", "xsalsa20_poly1305_lite"):
        return _xsalsa20_lite(
            header, payload, secret_key, nonce_counter,
            rtpsize=("rtpsize" in mode),
        )

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


@lru_cache(maxsize=4)
def _get_aesgcm(key: bytes) -> "AESGCM":
    """Return a cached :class:`AESGCM` instance for *key*."""
    if not _HAS_AES_GCM:
        raise ImportError(
            "cryptography package is required for aead_aes256_gcm_rtpsize"
        )
    return AESGCM(key)


def _aes256_gcm_rtpsize(
    header: bytes, payload: bytes, key: bytes, nonce_counter: int,
) -> bytes:
    """
    aead_aes256_gcm_rtpsize:
      nonce = 32-bit incrementing counter (big-endian) zero-padded to 12 bytes.
      The 4-byte counter is appended to the packet as the nonce suffix.
      additional_data = header
    """
    nonce_suffix = struct.pack(">I", nonce_counter & 0xFFFFFFFF)
    nonce = nonce_suffix + b"\x00" * 8  # 12-byte nonce
    aesgcm = _get_aesgcm(key)
    encrypted = aesgcm.encrypt(nonce, payload, header)
    return header + encrypted + nonce_suffix


def _xsalsa20_lite(
    header: bytes,
    payload: bytes,
    key: bytes,
    nonce_counter: int,
    rtpsize: bool,
) -> bytes:
    """
    xsalsa20_poly1305_lite / xsalsa20_poly1305_lite_rtpsize:
      nonce = monotonically incrementing 32-bit counter (little-endian),
              appended to the packet and zero-padded to 24 bytes for NaCl.
    """
    nonce_suffix = struct.pack("<I", nonce_counter & 0xFFFFFFFF)
    nonce = nonce_suffix + b"\x00" * 20  # 24-byte NaCl nonce
    box = SecretBox(key)
    encrypted = box.encrypt(payload, nonce=nonce).ciphertext
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
