from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import deque
from typing import Optional
import math


@dataclass
class ReadingResult:
    zone: str
    value: Optional[float]
    state: str
    confidence: str
    reason: str
    rate_of_change: Optional[float]
    timestamp: str


@dataclass
class ZoneState:
    name: str
    warning_threshold: float = 25.0
    danger_threshold: float = 40.0
    maximum_level: float = 50.0
    history: deque = field(default_factory=lambda: deque(maxlen=20))
    last_valid_value: Optional[float] = None
    last_valid_time: Optional[datetime] = None
    last_result: Optional[ReadingResult] = None


class MonitoringEngine:
    """
    Local monitoring engine for WaveGuard X.

    This version evaluates simulated or supplied readings.
    It does not connect to physical sensors or predict real floods.
    """

    def __init__(
        self,
        stale_after_seconds: int = 10,
        maximum_rate_per_second: float = 5.0
    ):
        self.stale_after_seconds = stale_after_seconds
        self.maximum_rate_per_second = maximum_rate_per_second
        self.zones: dict[str, ZoneState] = {}
        self.events: list[dict] = []

    def register_zone(
        self,
        name: str,
        warning_threshold: float = 25.0,
        danger_threshold: float = 40.0,
        maximum_level: float = 50.0
    ) -> None:
        if not name.strip():
            raise ValueError("Zone name cannot be empty.")

        if not (
            0 <= warning_threshold < danger_threshold <= maximum_level
        ):
            raise ValueError("Threshold configuration is invalid.")

        self.zones[name] = ZoneState(
            name=name,
            warning_threshold=warning_threshold,
            danger_threshold=danger_threshold,
            maximum_level=maximum_level
        )

        self._record_event(
            name,
            "ZONE_REGISTERED",
            "Monitoring zone registered."
        )

    def process_reading(
        self,
        zone_name: str,
        value: Optional[float],
        timestamp: Optional[datetime] = None
    ) -> ReadingResult:
        if zone_name not in self.zones:
            raise KeyError(f"Unknown monitoring zone: {zone_name}")

        zone = self.zones[zone_name]
        now = timestamp or datetime.now(timezone.utc)

        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        timestamp_text = now.isoformat()

        if value is None:
            return self._make_result(
                zone,
                None,
                "UNAVAILABLE",
                "NONE",
                "No reading was received.",
                None,
                timestamp_text
            )

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return self._make_result(
                zone,
                None,
                "INVALID",
                "NONE",
                "Reading must be a numeric value.",
                None,
                timestamp_text
            )

        value = float(value)

        if not math.isfinite(value):
            return self._make_result(
                zone,
                value,
                "INVALID",
                "NONE",
                "Reading must be a finite number.",
                None,
                timestamp_text
            )

        if value < 0 or value > zone.maximum_level:
            return self._make_result(
                zone,
                value,
                "INVALID",
                "NONE",
                "Reading is outside the configured range.",
                None,
                timestamp_text
            )

        previous_value = zone.last_valid_value
        previous_time = zone.last_valid_time
        rate = None

        if previous_value is not None and previous_time is not None:
            elapsed = (now - previous_time).total_seconds()

            if elapsed <= 0:
                return self._make_result(
                    zone,
                    value,
                    "INVALID",
                    "NONE",
                    "Reading timestamp must be later than the previous valid reading.",
                    None,
                    timestamp_text
                )

            rate = (value - previous_value) / elapsed

            if abs(rate) > self.maximum_rate_per_second:
                return self._make_result(
                    zone,
                    value,
                    "SUSPICIOUS",
                    "LOW",
                    "Unusually rapid change detected. Verify this reading.",
                    rate,
                    timestamp_text
                )

        zone.history.append({
            "value": value,
            "timestamp": timestamp_text
        })

        zone.last_valid_value = value
        zone.last_valid_time = now

        if value >= zone.danger_threshold:
            state = "DANGER"
            reason = "Reading crossed the configured danger threshold."
        elif value >= zone.warning_threshold:
            state = "WARNING"
            reason = "Reading crossed the configured warning threshold."
        else:
            state = "NORMAL"
            reason = "Reading is within the configured normal range."

        result = self._make_result(
            zone,
            value,
            state,
            "BASIC_VALIDATION_PASSED",
            reason,
            rate,
            timestamp_text
        )

        zone.last_result = result
        return result

    def get_zone_status(
        self,
        zone_name: str,
        now: Optional[datetime] = None
    ) -> dict:
        if zone_name not in self.zones:
            raise KeyError(f"Unknown monitoring zone: {zone_name}")

        zone = self.zones[zone_name]
        current_time = now or datetime.now(timezone.utc)

        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        if zone.last_valid_time is None:
            return {
                "zone": zone_name,
                "state": "UNAVAILABLE",
                "last_valid_value": None,
                "age_seconds": None,
                "reason": "No valid reading has been received."
            }

        age = (
            current_time - zone.last_valid_time
        ).total_seconds()

        if age < 0:
            return {
                "zone": zone_name,
                "state": "TIME_ERROR",
                "last_valid_value": zone.last_valid_value,
                "age_seconds": age,
                "reason": "Current time precedes the latest valid reading."
            }

        if age > self.stale_after_seconds:
            return {
                "zone": zone_name,
                "state": "STALE",
                "last_valid_value": zone.last_valid_value,
                "age_seconds": age,
                "reason": "The last valid reading is too old."
            }

        return {
            "zone": zone_name,
            "state": (
                zone.last_result.state
                if zone.last_result
                else "UNAVAILABLE"
            ),
            "last_valid_value": zone.last_valid_value,
            "age_seconds": age,
            "reason": (
                zone.last_result.reason
                if zone.last_result
                else "No current status is available."
            )
        }

    def get_history(self, zone_name: str) -> list[dict]:
        if zone_name not in self.zones:
            raise KeyError(f"Unknown monitoring zone: {zone_name}")

        return list(self.zones[zone_name].history)

    def get_events(self) -> list[dict]:
        return list(self.events)

    def _make_result(
        self,
        zone: ZoneState,
        value: Optional[float],
        state: str,
        confidence: str,
        reason: str,
        rate: Optional[float],
        timestamp: str
    ) -> ReadingResult:
        result = ReadingResult(
            zone=zone.name,
            value=value,
            state=state,
            confidence=confidence,
            reason=reason,
            rate_of_change=rate,
            timestamp=timestamp
        )

        self._record_event(
            zone.name,
            state,
            reason,
            value,
            timestamp
        )

        return result

    def _record_event(
        self,
        zone: str,
        event_type: str,
        message: str,
        value: Optional[float] = None,
        timestamp: Optional[str] = None
    ) -> None:
        self.events.append({
            "zone": zone,
            "event": event_type,
            "message": message,
            "value": value,
            "timestamp": timestamp or datetime.now(
                timezone.utc
            ).isoformat()
        })