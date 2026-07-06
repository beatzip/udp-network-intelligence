"""Abstract base for all wire protocol encoders/decoders.

Defines the ``BaseProtocol`` ABC that every protocol module
(Source Query, A2S, ICMP, IP) must implement. Provides a uniform
encode/decode interface and common validation helpers.

Example::

    class MyProtocol(BaseProtocol):
        def encode_request(self, **kwargs) -> bytes:
            ...
        def decode_response(self, data: bytes) -> Any:
            ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class ProtocolError(Exception):
    """Raised when a protocol-level error occurs."""


class ProtocolValidationError(ProtocolError):
    """Raised when a received packet fails validation."""


class ProtocolTimeout(ProtocolError):
    """Raised when a protocol exchange times out."""


class PacketDirection(Enum):
    """Direction of a packet relative to the application."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"

    def to_dict(self) -> str:
        """Serialize to string."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> PacketDirection:
        """Deserialize from string."""
        return cls(value)


class BaseProtocol(ABC):
    """Abstract base class for wire protocol implementations.

    Every concrete protocol must implement ``encode_request`` and
    ``decode_response``. Optional overrides: ``validate``,
    ``encode_challenge_request``.

    Attributes:
        HEADER: Expected header bytes for this protocol.
        TIMEOUT: Default timeout in seconds.
    """

    HEADER: bytes = b""
    TIMEOUT: float = 5.0

    @abstractmethod
    def encode_request(self, **kwargs: Any) -> bytes:
        """Encode a request packet.

        Args:
            **kwargs: Protocol-specific request parameters.

        Returns:
            Encoded packet bytes ready to send.
        """

    @abstractmethod
    def decode_response(self, data: bytes) -> Any:
        """Decode a response packet.

        Args:
            data: Raw response bytes.

        Returns:
            Decoded protocol-specific result.

        Raises:
            ProtocolValidationError: If the packet is malformed.
        """

    def validate(self, data: bytes) -> bool:
        """Validate an A2S packet.

        Args:
            data: Raw packet bytes.

        Returns:
            True if the packet matches the expected format.
        """
        if not data or len(data) < len(self.HEADER):
            return False
        return not (self.HEADER and data[: len(self.HEADER)] != self.HEADER)

    def validate_header(self, data: bytes) -> None:
        """Raise if the packet header is wrong.

        Args:
            data: Raw packet bytes.

        Raises:
            ProtocolValidationError: If header mismatch.
        """
        if not self.validate(data):
            raise ProtocolValidationError(
                f"Invalid header: expected {self.HEADER!r}, "
                f"got {data[: len(self.HEADER)]!r}"
            )
