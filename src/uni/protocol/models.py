"""Wire protocol data models — IP, ICMP, A2S, and generic packet structures.

Defines the data structures for parsed network packets at various layers:
IPv4 headers, ICMP messages, A2S query packets, and generic packet wrappers.

All dataclasses support JSON round-tripping via ``to_dict()`` / ``from_dict()``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Self

from uni.app.constants import A2S_HEADER_SIZE, IP_HEADER_MIN_LENGTH, ICMPType


class PacketDirection(Enum):
    """Direction of a packet relative to the application."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"

    def to_dict(self) -> str:
        """Serialize to JSON-compatible string."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> Self:
        """Deserialize from a string value.

        Args:
            value: Direction string.

        Returns:
            Corresponding enum member.
        """
        return cls(value)


class A2SRequestType(Enum):
    """A2S query request types."""

    INFO = 0x54  # 'T'
    PLAYER = 0x55  # 'U'
    RULES = 0x56  # 'V'

    def to_dict(self) -> int:
        """Serialize to JSON-compatible integer."""
        return self.value

    @classmethod
    def from_dict(cls, value: int) -> Self:
        """Deserialize from an integer value.

        Args:
            value: A2S request type byte.

        Returns:
            Corresponding enum member.

        Raises:
            ValueError: If the value is not a valid request type.
        """
        return cls(value)


class A2SResponseType(Enum):
    """A2S query response types."""

    INFO = 0x49  # 'I'
    PLAYER = 0x44  # 'D'
    RULES = 0x45  # 'E'
    CHALLENGE = 0x41  # 'A'
    GOLDSOURCE_INFO = 0x6D  # 'm' (GoldSource engine)
    GOLDSOURCE_PLAYER = 0x6E  # 'n'
    GOLDSOURCE_RULES = 0x6F  # 'o'

    def to_dict(self) -> int:
        """Serialize to JSON-compatible integer."""
        return self.value

    @classmethod
    def from_dict(cls, value: int) -> Self:
        """Deserialize from an integer value.

        Args:
            value: A2S response type byte.

        Returns:
            Corresponding enum member.
        """
        return cls(value)


@dataclass(frozen=True, slots=True)
class IPHeader:
    """Parsed IPv4 header.

    Represents the standard 20-byte IPv4 header extracted from
    captured packets.

    Attributes:
        version: IP version (always 4).
        ihl: Internet Header Length in bytes (min 20).
        dscp: Differentiated Services Code Point.
        ecn: Explicit Congestion Notification.
        total_length: Total packet length in bytes.
        identification: Packet identification field.
        flags: IP flags (DF, MF).
        fragment_offset: Fragment offset.
        ttl: Time To Live.
        protocol: Transport protocol number (17 = UDP, 1 = ICMP).
        checksum: Header checksum.
        src_ip: Source IP address.
        dst_ip: Destination IP address.

    Example::

        >>> header = IPHeader(ttl=64, protocol=17, src_ip="10.0.0.1", dst_ip="8.8.8.8")
        >>> header.is_udp
        True
    """

    version: int = 4
    ihl: int = IP_HEADER_MIN_LENGTH
    dscp: int = 0
    ecn: int = 0
    total_length: int = 0
    identification: int = 0
    flags: int = 0
    fragment_offset: int = 0
    ttl: int = 64
    protocol: int = 0
    checksum: int = 0
    src_ip: str = ""
    dst_ip: str = ""

    def __post_init__(self) -> None:
        """Validate IP header fields."""
        if not (4 <= self.version <= 6):
            raise ValueError(f"IPHeader.version must be 4 or 6, got {self.version}")
        if self.ihl < IP_HEADER_MIN_LENGTH:
            raise ValueError(
                f"IPHeader.ihl must be >= {IP_HEADER_MIN_LENGTH}, got {self.ihl}"
            )
        if not (0 <= self.ttl <= 255):
            raise ValueError(f"IPHeader.ttl must be 0-255, got {self.ttl}")
        if not (0 <= self.protocol <= 255):
            raise ValueError(f"IPHeader.protocol must be 0-255, got {self.protocol}")

    @property
    def is_udp(self) -> bool:
        """True if protocol is UDP (17)."""
        return self.protocol == 17

    @property
    def is_tcp(self) -> bool:
        """True if protocol is TCP (6)."""
        return self.protocol == 6

    @property
    def is_icmp(self) -> bool:
        """True if protocol is ICMP (1)."""
        return self.protocol == 1

    @property
    def header_length(self) -> int:
        """Header length in bytes (IHL * 4)."""
        return self.ihl

    @property
    def options_length(self) -> int:
        """Length of IP options in bytes."""
        return max(0, self.ihl - IP_HEADER_MIN_LENGTH)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary with all header fields.
        """
        return {
            "version": self.version,
            "ihl": self.ihl,
            "dscp": self.dscp,
            "ecn": self.ecn,
            "total_length": self.total_length,
            "identification": self.identification,
            "flags": self.flags,
            "fragment_offset": self.fragment_offset,
            "ttl": self.ttl,
            "protocol": self.protocol,
            "checksum": self.checksum,
            "src_ip": self.src_ip,
            "dst_ip": self.dst_ip,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with IP header fields.

        Returns:
            IPHeader instance.
        """
        return cls(
            version=int(data.get("version", 4)),
            ihl=int(data.get("ihl", IP_HEADER_MIN_LENGTH)),
            dscp=int(data.get("dscp", 0)),
            ecn=int(data.get("ecn", 0)),
            total_length=int(data.get("total_length", 0)),
            identification=int(data.get("identification", 0)),
            flags=int(data.get("flags", 0)),
            fragment_offset=int(data.get("fragment_offset", 0)),
            ttl=int(data.get("ttl", 64)),
            protocol=int(data.get("protocol", 0)),
            checksum=int(data.get("checksum", 0)),
            src_ip=str(data.get("src_ip", "")),
            dst_ip=str(data.get("dst_ip", "")),
        )


@dataclass(frozen=True, slots=True)
class ICMPMessage:
    """Parsed ICMP message.

    Represents an ICMPv4 message with type, code, and embedded data.
    Used for traceroute analysis and error detection.

    Attributes:
        icmp_type: ICMP message type (RFC 792).
        code: ICMP code (sub-type).
        checksum: ICMP checksum.
        rest_of_header: First 4 bytes after the type/code/checksum.
        embedded_header: Embedded IP header + 8 bytes (for errors).
        src_ip: Source IP of the ICMP message.
        dst_ip: Destination IP of the ICMP message.

    Example::

        >>> msg = ICMPMessage(icmp_type=11, code=0, src_ip="10.0.0.1")
        >>> msg.is_time_exceeded
        True
    """

    icmp_type: int = 0
    code: int = 0
    checksum: int = 0
    rest_of_header: int = 0
    embedded_header: bytes = b""
    src_ip: str = ""
    dst_ip: str = ""

    def __post_init__(self) -> None:
        """Validate ICMP message fields."""
        if not (0 <= self.icmp_type <= 255):
            raise ValueError(
                f"ICMPMessage.icmp_type must be 0-255, got {self.icmp_type}"
            )
        if not (0 <= self.code <= 255):
            raise ValueError(f"ICMPMessage.code must be 0-255, got {self.code}")

    @property
    def is_echo_reply(self) -> bool:
        """True if this is an Echo Reply (type 0)."""
        return self.icmp_type == ICMPType.ECHO_REPLY.value

    @property
    def is_echo_request(self) -> bool:
        """True if this is an Echo Request (type 8)."""
        return self.icmp_type == ICMPType.ECHO_REQUEST.value

    @property
    def is_dest_unreachable(self) -> bool:
        """True if this is a Destination Unreachable (type 3)."""
        return self.icmp_type == ICMPType.DEST_UNREACHABLE.value

    @property
    def is_time_exceeded(self) -> bool:
        """True if this is a Time Exceeded message (type 11)."""
        return self.icmp_type == ICMPType.TIME_EXCEEDED.value

    @property
    def is_redirect(self) -> bool:
        """True if this is a Redirect message (type 5)."""
        return self.icmp_type == ICMPType.REDIRECT.value

    @property
    def is_error(self) -> bool:
        """True if this is an ICMP error message (types 3, 4, 5, 11, 12)."""
        return self.icmp_type in (3, 4, 5, 11, 12)

    @property
    def type_name(self) -> str:
        """Human-readable ICMP type name."""
        names = {
            0: "Echo Reply",
            3: "Destination Unreachable",
            4: "Source Quench",
            5: "Redirect",
            8: "Echo Request",
            11: "Time Exceeded",
            12: "Parameter Problem",
            13: "Timestamp",
            14: "Timestamp Reply",
        }
        return names.get(self.icmp_type, f"Unknown ({self.icmp_type})")

    @property
    def embedded_src_ip(self) -> str | None:
        """Source IP from the embedded IP header (for error messages).

        Returns None if the embedded header is too short.
        """
        if len(self.embedded_header) < 20:
            return None
        # Source IP is at offset 12 in the embedded IPv4 header
        return ".".join(str(b) for b in self.embedded_header[12:16])

    @property
    def embedded_dst_ip(self) -> str | None:
        """Destination IP from the embedded IP header (for error messages).

        Returns None if the embedded header is too short.
        """
        if len(self.embedded_header) < 20:
            return None
        # Destination IP is at offset 16 in the embedded IPv4 header
        return ".".join(str(b) for b in self.embedded_header[16:20])

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Bytes fields are serialized as lists of integers.

        Returns:
            Dictionary with all ICMP message fields.
        """
        return {
            "icmp_type": self.icmp_type,
            "code": self.code,
            "checksum": self.checksum,
            "rest_of_header": self.rest_of_header,
            "embedded_header": list(self.embedded_header),
            "src_ip": self.src_ip,
            "dst_ip": self.dst_ip,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with ICMP message fields.

        Returns:
            ICMPMessage instance.
        """
        embedded = data.get("embedded_header", [])
        return cls(
            icmp_type=int(data.get("icmp_type", 0)),
            code=int(data.get("code", 0)),
            checksum=int(data.get("checksum", 0)),
            rest_of_header=int(data.get("rest_of_header", 0)),
            embedded_header=bytes(embedded) if isinstance(embedded, list) else b"",
            src_ip=str(data.get("src_ip", "")),
            dst_ip=str(data.get("dst_ip", "")),
        )


@dataclass(frozen=True, slots=True)
class A2SPacket:
    """Parsed A2S (Source Engine) query/response packet.

    Represents a single A2S protocol packet with header, payload,
    and optional challenge number.

    Attributes:
        header: Packet type header byte.
        payload: Raw packet payload.
        challenge: Challenge number (for challenge-response handshake).
        request_type: A2S request type (for request packets).
        response_type: A2S response type (for response packets).
        packet_size: Total packet size in bytes.

    Example::

        >>> packet = A2SPacket(
        ...     header=0x49,
        ...     payload=b"\\xff\\xff\\xff\\xff...",
        ...     packet_size=48,
        ... )
        >>> packet.is_info_response
        True
    """

    header: int = 0
    payload: bytes = b""
    challenge: int = 0
    request_type: A2SRequestType | None = None
    response_type: A2SResponseType | None = None
    packet_size: int = 0

    def __post_init__(self) -> None:
        """Validate A2S packet fields."""
        if self.packet_size == 0:
            # Auto-calculate from header + payload
            object.__setattr__(self, "packet_size", A2S_HEADER_SIZE + len(self.payload))

    @property
    def is_info_response(self) -> bool:
        """True if this is an A2S_INFO response."""
        return self.header == 0x49

    @property
    def is_player_response(self) -> bool:
        """True if this is an A2S_PLAYER response."""
        return self.header == 0x44

    @property
    def is_rules_response(self) -> bool:
        """True if this is an A2S_RULES response."""
        return self.header == 0x45

    @property
    def is_challenge_response(self) -> bool:
        """True if this is an A2S challenge response."""
        return self.header == 0x41

    @property
    def is_info_request(self) -> bool:
        """True if this is an A2S_INFO request."""
        return self.request_type == A2SRequestType.INFO

    @property
    def is_player_request(self) -> bool:
        """True if this is an A2S_PLAYER request."""
        return self.request_type == A2SRequestType.PLAYER

    @property
    def is_rules_request(self) -> bool:
        """True if this is an A2S_RULES request."""
        return self.request_type == A2SRequestType.RULES

    @property
    def has_challenge(self) -> bool:
        """True if a challenge number is present."""
        return self.challenge != 0 and self.challenge != -1

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Bytes payload is serialized as a list of integers.

        Returns:
            Dictionary with all packet fields.
        """
        return {
            "header": self.header,
            "payload": list(self.payload),
            "challenge": self.challenge,
            "request_type": self.request_type.value if self.request_type else None,
            "response_type": (self.response_type.value if self.response_type else None),
            "packet_size": self.packet_size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with A2S packet fields.

        Returns:
            A2SPacket instance.
        """
        req_raw = data.get("request_type")
        resp_raw = data.get("response_type")
        payload_raw = data.get("payload", [])
        return cls(
            header=int(data.get("header", 0)),
            payload=bytes(payload_raw) if isinstance(payload_raw, list) else b"",
            challenge=int(data.get("challenge", 0)),
            request_type=(A2SRequestType(req_raw) if req_raw is not None else None),
            response_type=(A2SResponseType(resp_raw) if resp_raw is not None else None),
            packet_size=int(data.get("packet_size", 0)),
        )


@dataclass(frozen=True, slots=True)
class Packet:
    """Generic network packet wrapper.

    Wraps raw packet data with metadata about source/destination,
    timing, and direction. Used as a transport-layer abstraction
    across the protocol stack.

    Attributes:
        data: Raw packet bytes.
        source_ip: Source IP address.
        source_port: Source port number.
        dest_ip: Destination IP address.
        dest_port: Destination port number.
        timestamp: Unix timestamp when the packet was captured.
        direction: Packet direction (inbound/outbound).
        capture_length: Number of bytes actually captured.
        original_length: Original packet length on the wire.

    Example::

        >>> pkt = Packet(
        ...     data=b"\\x00\\x01\\x02",
        ...     source_ip="10.0.0.1",
        ...     source_port=12345,
        ...     dest_ip="8.8.8.8",
        ...     dest_port=27015,
        ... )
        >>> pkt.size
        3
    """

    data: bytes = b""
    source_ip: str = ""
    source_port: int = 0
    dest_ip: str = ""
    dest_port: int = 0
    timestamp: float = field(default_factory=time.time)
    direction: PacketDirection = PacketDirection.OUTBOUND
    capture_length: int = 0
    original_length: int = 0

    def __post_init__(self) -> None:
        """Validate packet fields and auto-set capture_length."""
        if self.capture_length == 0:
            object.__setattr__(self, "capture_length", len(self.data))
        if self.original_length == 0:
            object.__setattr__(self, "original_length", len(self.data))
        if self.source_port < 0 or self.source_port > 65535:
            raise ValueError(
                f"Packet.source_port must be 0-65535, got {self.source_port}"
            )
        if self.dest_port < 0 or self.dest_port > 65535:
            raise ValueError(f"Packet.dest_port must be 0-65535, got {self.dest_port}")

    @property
    def size(self) -> int:
        """Size of the packet data in bytes."""
        return len(self.data)

    @property
    def is_empty(self) -> bool:
        """True if the packet has no data."""
        return len(self.data) == 0

    @property
    def hex_dump(self) -> str:
        """Hex dump of the packet data."""
        return self.data.hex(" ")

    @property
    def source(self) -> str:
        """Source as ``ip:port`` string."""
        return f"{self.source_ip}:{self.source_port}"

    @property
    def destination(self) -> str:
        """Destination as ``ip:port`` string."""
        return f"{self.dest_ip}:{self.dest_port}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Data bytes are serialized as a list of integers.

        Returns:
            Dictionary with all packet fields.
        """
        return {
            "data": list(self.data),
            "source_ip": self.source_ip,
            "source_port": self.source_port,
            "dest_ip": self.dest_ip,
            "dest_port": self.dest_port,
            "timestamp": self.timestamp,
            "direction": self.direction.value,
            "capture_length": self.capture_length,
            "original_length": self.original_length,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with packet fields.

        Returns:
            Packet instance.
        """
        raw_data = data.get("data", [])
        return cls(
            data=bytes(raw_data) if isinstance(raw_data, list) else b"",
            source_ip=str(data.get("source_ip", "")),
            source_port=int(data.get("source_port", 0)),
            dest_ip=str(data.get("dest_ip", "")),
            dest_port=int(data.get("dest_port", 0)),
            timestamp=float(data.get("timestamp", 0.0)),
            direction=PacketDirection(data.get("direction", "outbound")),
            capture_length=int(data.get("capture_length", 0)),
            original_length=int(data.get("original_length", 0)),
        )
