"""Statistical analysis data models — quality reports, anomalies, and results.

Defines the data structures for probe analysis: connection quality
assessment (A-F grades), detected anomaly events, and aggregated
analysis results.

All dataclasses support JSON round-tripping via ``to_dict()`` / ``from_dict()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Self

from uni.app.constants import AnomalyType, QualityGrade


@dataclass(frozen=True, slots=True)
class AnomalyEvent:
    """Detected network anomaly during probe analysis.

    Represents a single anomalous event identified by the anomaly
    detector: a latency spike, packet loss burst, jitter spike,
    or unstable connection pattern.

    Attributes:
        anomaly_type: Type of anomaly detected.
        timestamp: When the anomaly was detected (UTC).
        value: Measured value that triggered the anomaly.
        threshold: Threshold that was exceeded.
        description: Human-readable description of the anomaly.
        severity: Severity level (1 = low, 5 = critical).
        sequence: Probe sequence number where the anomaly occurred.

    Example::

        >>> event = AnomalyEvent(
        ...     anomaly_type=AnomalyType.LATENCY_SPIKE,
        ...     timestamp=datetime.now(timezone.utc),
        ...     value=250.0,
        ...     threshold=100.0,
        ...     description="Latency spike detected: 250.0ms > 100.0ms",
        ... )
        >>> event.severity_label
        'medium'
    """

    anomaly_type: AnomalyType
    timestamp: datetime
    value: float
    threshold: float
    description: str = ""
    severity: int = 3
    sequence: int = -1

    def __post_init__(self) -> None:
        """Validate anomaly event fields."""
        if not (1 <= self.severity <= 5):
            raise ValueError(
                f"AnomalyEvent.severity must be 1-5, got {self.severity}"
            )
        if self.threshold <= 0:
            raise ValueError(
                f"AnomalyEvent.threshold must be > 0, got {self.threshold}"
            )

    @property
    def excess_ratio(self) -> float:
        """How much the value exceeds the threshold (as a ratio).

        A value of 2.0 means the measured value is 2x the threshold.
        """
        if self.threshold <= 0:
            return 0.0
        return self.value / self.threshold

    @property
    def severity_label(self) -> str:
        """Human-readable severity label."""
        labels = {1: "low", 2: "low", 3: "medium", 4: "high", 5: "critical"}
        return labels.get(self.severity, "unknown")

    @property
    def is_critical(self) -> bool:
        """True if severity is 4 or 5."""
        return self.severity >= 4

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Datetime is serialized to ISO 8601 format.

        Returns:
            Dictionary with all anomaly event fields.
        """
        return {
            "anomaly_type": self.anomaly_type.value,
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "threshold": self.threshold,
            "description": self.description,
            "severity": self.severity,
            "sequence": self.sequence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with anomaly event fields.

        Returns:
            AnomalyEvent instance.

        Raises:
            KeyError: If required fields are missing.
        """
        ts_raw = data.get("timestamp", "")
        if isinstance(ts_raw, str) and ts_raw:
            try:
                timestamp = datetime.fromisoformat(ts_raw)
            except ValueError:
                timestamp = datetime.now(UTC)
        elif isinstance(ts_raw, datetime):
            timestamp = ts_raw
        else:
            timestamp = datetime.now(UTC)

        return cls(
            anomaly_type=AnomalyType(data["anomaly_type"]),
            timestamp=timestamp,
            value=float(data["value"]),
            threshold=float(data["threshold"]),
            description=str(data.get("description", "")),
            severity=int(data.get("severity", 3)),
            sequence=int(data.get("sequence", -1)),
        )


@dataclass(frozen=True, slots=True)
class QualityReport:
    """Connection quality assessment.

    Contains the overall quality grade and individual component scores
    used to compute it. Scores range from 0.0 (worst) to 100.0 (best).

    Attributes:
        grade: Overall quality grade (A+ through F).
        latency_score: Score based on average latency (0-100).
        loss_score: Score based on packet loss (0-100).
        jitter_score: Score based on jitter (0-100).
        overall_score: Weighted average of all component scores.
        avg_rtt_ms: Average latency used for grading.
        loss_percent: Packet loss percentage used for grading.
        jitter_ms: Average jitter used for grading.

    Example::

        >>> report = QualityReport(
        ...     grade=QualityGrade.A,
        ...     latency_score=90.0,
        ...     loss_score=95.0,
        ...     jitter_score=85.0,
        ...     overall_score=90.0,
        ... )
        >>> report.grade
        <QualityGrade.A: 'A'>
    """

    grade: QualityGrade = QualityGrade.C
    latency_score: float = 0.0
    loss_score: float = 0.0
    jitter_score: float = 0.0
    overall_score: float = 0.0
    avg_rtt_ms: float = 0.0
    loss_percent: float = 0.0
    jitter_ms: float = 0.0

    def __post_init__(self) -> None:
        """Validate quality report fields."""
        score_fields = ("latency_score", "loss_score", "jitter_score", "overall_score")
        for field_name in score_fields:
            val = getattr(self, field_name)
            if not (0.0 <= val <= 100.0):
                raise ValueError(
                    f"QualityReport.{field_name} must be 0.0-100.0, got {val}"
                )
        if self.avg_rtt_ms < 0:
            raise ValueError(
                f"QualityReport.avg_rtt_ms must be >= 0, got {self.avg_rtt_ms}"
            )
        if self.loss_percent < 0 or self.loss_percent > 100:
            raise ValueError(
                f"QualityReport.loss_percent must be 0-100, got {self.loss_percent}"
            )
        if self.jitter_ms < 0:
            raise ValueError(
                f"QualityReport.jitter_ms must be >= 0, got {self.jitter_ms}"
            )

    @property
    def is_excellent(self) -> bool:
        """True if grade is A+ or A."""
        return self.grade in (QualityGrade.A_PLUS, QualityGrade.A)

    @property
    def is_good(self) -> bool:
        """True if grade is B+ or better."""
        return self.grade.numeric_value >= 6

    @property
    def is_acceptable(self) -> bool:
        """True if grade is C+ or better."""
        return self.grade.numeric_value >= 4

    @property
    def is_poor(self) -> bool:
        """True if grade is D or F."""
        return self.grade.numeric_value <= 2

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary with all quality report fields.
        """
        return {
            "grade": self.grade.value,
            "latency_score": round(self.latency_score, 2),
            "loss_score": round(self.loss_score, 2),
            "jitter_score": round(self.jitter_score, 2),
            "overall_score": round(self.overall_score, 2),
            "avg_rtt_ms": round(self.avg_rtt_ms, 2),
            "loss_percent": round(self.loss_percent, 2),
            "jitter_ms": round(self.jitter_ms, 2),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with quality report fields.

        Returns:
            QualityReport instance.
        """
        return cls(
            grade=QualityGrade(data.get("grade", "C")),
            latency_score=float(data.get("latency_score", 0.0)),
            loss_score=float(data.get("loss_score", 0.0)),
            jitter_score=float(data.get("jitter_score", 0.0)),
            overall_score=float(data.get("overall_score", 0.0)),
            avg_rtt_ms=float(data.get("avg_rtt_ms", 0.0)),
            loss_percent=float(data.get("loss_percent", 0.0)),
            jitter_ms=float(data.get("jitter_ms", 0.0)),
        )


@dataclass
class AnalysisResult:
    """Full analysis result combining quality assessment and anomalies.

    Produced by the analysis pipeline after processing all probe
    results from a campaign. Contains the quality report, detected
    anomalies, and metadata about the analysis.

    Attributes:
        quality: Connection quality assessment.
        anomalies: List of detected anomaly events.
        sample_count: Number of probe samples analyzed.
        duration_seconds: Duration of the probe campaign.
        target: Target that was analyzed.
        start_time: When the analysis started.
        end_time: When the analysis completed.

    Example::

        >>> result = AnalysisResult(target="1.2.3.4:27015", sample_count=50)
        >>> result.anomaly_count
        0
    """

    quality: QualityReport = field(default_factory=QualityReport)
    anomalies: list[AnomalyEvent] = field(default_factory=list)
    sample_count: int = 0
    duration_seconds: float = 0.0
    target: str = ""
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def anomaly_count(self) -> int:
        """Number of detected anomalies."""
        return len(self.anomalies)

    @property
    def critical_anomalies(self) -> list[AnomalyEvent]:
        """Only anomalies with severity >= 4."""
        return [a for a in self.anomalies if a.is_critical]

    @property
    def critical_count(self) -> int:
        """Number of critical anomalies."""
        return len(self.critical_anomalies)

    @property
    def anomalies_by_type(self) -> dict[AnomalyType, int]:
        """Count of anomalies grouped by type."""
        counts: dict[AnomalyType, int] = {}
        for a in self.anomalies:
            counts[a.anomaly_type] = counts.get(a.anomaly_type, 0) + 1
        return counts

    @property
    def is_anomaly_free(self) -> bool:
        """True if no anomalies were detected."""
        return len(self.anomalies) == 0

    @property
    def duration_minutes(self) -> float:
        """Duration in minutes."""
        return self.duration_seconds / 60.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary with all analysis result fields.
        """
        return {
            "quality": self.quality.to_dict(),
            "anomalies": [a.to_dict() for a in self.anomalies],
            "sample_count": self.sample_count,
            "duration_seconds": round(self.duration_seconds, 2),
            "target": self.target,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with analysis result fields.

        Returns:
            AnalysisResult instance.
        """
        quality_data = data.get("quality", {})
        anomalies_data = data.get("anomalies", [])
        return cls(
            quality=QualityReport.from_dict(quality_data),
            anomalies=[AnomalyEvent.from_dict(a) for a in anomalies_data],
            sample_count=int(data.get("sample_count", 0)),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            target=str(data.get("target", "")),
            start_time=float(data.get("start_time", 0.0)),
            end_time=float(data.get("end_time", 0.0)),
        )
