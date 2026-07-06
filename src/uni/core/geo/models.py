"""GeoIP data models — geographic coordinates and IP location information.

Defines the data structures for IP geolocation data: coordinates,
country/city information, and ASN data.

All dataclasses support JSON round-tripping via ``to_dict()`` / ``from_dict()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self


@dataclass(frozen=True, slots=True)
class Coordinates:
    """Geographic coordinates (latitude/longitude).

    Uses WGS 84 coordinate system (standard for GPS and mapping).

    Attributes:
        latitude: Latitude in decimal degrees (-90.0 to 90.0).
        longitude: Longitude in decimal degrees (-180.0 to 180.0).

    Example::

        >>> coords = Coordinates(latitude=55.7558, longitude=37.6173)
        >>> coords.latitude
        55.7558
    """

    latitude: float = 0.0
    longitude: float = 0.0

    def __post_init__(self) -> None:
        """Validate coordinate ranges."""
        if not (-90.0 <= self.latitude <= 90.0):
            raise ValueError(
                f"Coordinates.latitude must be -90.0 to 90.0, got {self.latitude}"
            )
        if not (-180.0 <= self.longitude <= 180.0):
            raise ValueError(
                f"Coordinates.longitude must be -180.0 to 180.0, got {self.longitude}"
            )

    @property
    def is_valid(self) -> bool:
        """True if coordinates are non-zero (actual location)."""
        return self.latitude != 0.0 or self.longitude != 0.0

    @property
    def is_northern(self) -> bool:
        """True if in the northern hemisphere."""
        return self.latitude >= 0.0

    @property
    def is_eastern(self) -> bool:
        """True if in the eastern hemisphere."""
        return self.longitude >= 0.0

    @property
    def hemisphere(self) -> str:
        """Hemisphere label (e.g. ``"NE"``, ``"SW"``)."""
        ns = "N" if self.is_northern else "S"
        ew = "E" if self.is_eastern else "W"
        return f"{ns}{ew}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            ``{"latitude": ..., "longitude": ...}``
        """
        return {
            "latitude": round(self.latitude, 6),
            "longitude": round(self.longitude, 6),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with ``latitude`` and ``longitude`` keys.

        Returns:
            Coordinates instance.
        """
        return cls(
            latitude=float(data.get("latitude", 0.0)),
            longitude=float(data.get("longitude", 0.0)),
        )


@dataclass(frozen=True, slots=True)
class GeoInfo:
    """Geolocation information for an IP address.

    Contains country, city, region, and ASN data resolved from an
    IP address using a GeoIP database (e.g. MaxMind GeoLite2).

    Attributes:
        country_code: ISO 3166-1 alpha-2 country code (e.g. ``"US"``).
        country_name: Full country name (e.g. ``"United States"``).
        city: City name (e.g. ``"New York"``).
        region: Region/state name (e.g. ``"New York"``).
        asn: Autonomous System Number (e.g. ``15169``).
        as_org: AS organization name (e.g. ``"Google LLC"``).
        coordinates: Geographic coordinates.

    Example::

        >>> geo = GeoInfo(
        ...     country_code="US",
        ...     country_name="United States",
        ...     city="New York",
        ...     coordinates=Coordinates(latitude=40.7128, longitude=-74.0060),
        ... )
        >>> geo.has_data
        True
    """

    country_code: str = ""
    country_name: str = ""
    city: str = ""
    region: str = ""
    asn: int = 0
    as_org: str = ""
    coordinates: Coordinates = field(default_factory=Coordinates)

    def __post_init__(self) -> None:
        """Validate geo info fields."""
        if (
            self.country_code
            and len(self.country_code) != 2
            and not self.country_code.isalpha()
        ):
            raise ValueError(
                f"GeoInfo.country_code must be a 2-letter ISO code, "
                f"got {self.country_code!r}"
            )
        if self.asn < 0:
            raise ValueError(f"GeoInfo.asn must be >= 0, got {self.asn}")

    @property
    def has_data(self) -> bool:
        """True if any geo data is available."""
        return bool(self.country_code or self.city or self.asn)

    @property
    def has_country(self) -> bool:
        """True if country data is available."""
        return bool(self.country_code and self.country_name)

    @property
    def has_coordinates(self) -> bool:
        """True if coordinates are non-zero."""
        return self.coordinates.is_valid

    @property
    def display_location(self) -> str:
        """Human-readable location string (e.g. ``"New York, US"``)."""
        parts = []
        if self.city:
            parts.append(self.city)
        if self.country_code:
            parts.append(self.country_code)
        return ", ".join(parts) if parts else "Unknown"

    @property
    def flag_emoji(self) -> str:
        """Country flag emoji from ISO 3166-1 alpha-2 code.

        Returns empty string if code is unavailable.
        """
        if not self.country_code or len(self.country_code) != 2:
            return ""
        # Regional Indicator Symbol: base + letter offset
        base = ord("\U0001f1e6") - ord("A")
        return chr(base + ord(self.country_code[0])) + chr(
            base + ord(self.country_code[1])
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary with all geo info fields.
        """
        return {
            "country_code": self.country_code,
            "country_name": self.country_name,
            "city": self.city,
            "region": self.region,
            "asn": self.asn,
            "as_org": self.as_org,
            "coordinates": self.coordinates.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with geo info fields.

        Returns:
            GeoInfo instance.
        """
        coords_data = data.get("coordinates", {})
        return cls(
            country_code=str(data.get("country_code", "")),
            country_name=str(data.get("country_name", "")),
            city=str(data.get("city", "")),
            region=str(data.get("region", "")),
            asn=int(data.get("asn", 0)),
            as_org=str(data.get("as_org", "")),
            coordinates=Coordinates.from_dict(coords_data),
        )
