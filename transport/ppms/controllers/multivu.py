"""Quantum Design MultiPyVu sample-environment controller."""

from __future__ import annotations

import importlib
import math
import socket
import threading
from typing import Callable

from transport.ppms.protocol import (
    validate_ppms_field_command,
    validate_ppms_temperature_command,
)


class PPMSMultiVuReadbackController:
    """PPMS sample-environment client using official Quantum Design MultiPyVu."""

    def __init__(self, logger: Callable[[str], None]) -> None:
        self.logger = logger
        self.client = None
        self.host = ""
        self.port = 0
        self.lock = threading.RLock()

    @property
    def connected(self) -> bool:
        return self.client is not None

    @staticmethod
    def validate_endpoint(host: str, port: int) -> tuple[str, int]:
        host = str(host).strip()
        if not host:
            raise ValueError("PPMS IP address cannot be empty")
        try:
            socket.getaddrinfo(host, int(port), type=socket.SOCK_STREAM)
        except (OSError, ValueError) as error:
            raise ValueError(f"PPMS IP address or port is invalid: {host}:{port}") from error
        port = int(port)
        if not 1 <= port <= 65535:
            raise ValueError("PPMS TCP port must be between 1 and 65535")
        return host, port

    def connect(self, host: str, port: int) -> dict[str, object]:
        host, port = self.validate_endpoint(host, port)
        with self.lock:
            if self.client is not None:
                return self.read_environment()
            try:
                module = importlib.import_module("MultiPyVu")
            except ImportError as error:
                raise RuntimeError(
                    "Quantum Design MultiPyVu is missing; please run on this machine:\n"
                    "py -m pip install --upgrade MultiPyVu\n\n"
                    "and start MultiVu and the MultiPyVu Server on the PPMS host."
                ) from error
            client = module.Client(host=host, port=port)
            try:
                client.open()
                self.client = client
                self.host = host
                self.port = port
                result = self.read_environment()
            except BaseException:
                try:
                    client.close_client()
                except BaseException:
                    pass
                self.client = None
                raise
            self.logger(f"PPMS MultiVu connected: {host}:{port}")
            return result

    def read_environment(self) -> dict[str, object]:
        with self.lock:
            if self.client is None:
                raise RuntimeError("PPMS MultiVu is not connected")
            temperature_k, temperature_status = self.client.get_temperature()
            field_oe, field_status = self.client.get_field()
        temperature_k = float(temperature_k)
        field_oe = float(field_oe)
        if not math.isfinite(temperature_k) or not math.isfinite(field_oe):
            raise RuntimeError(
                f"PPMS returned non-finite readings: T={temperature_k!r}, H={field_oe!r}"
            )
        return {
            "temperature_k": temperature_k,
            "temperature_status": getattr(
                temperature_status, "name", str(temperature_status)
            ),
            "field_oe": field_oe,
            "field_status": getattr(field_status, "name", str(field_status)),
        }

    @staticmethod
    def _enum_member(client, modern_group: str, legacy_group: str, name: str):
        group = getattr(client, modern_group, None)
        if group is not None:
            nested = getattr(group, "approach_mode", None)
            if nested is not None and hasattr(nested, name):
                return getattr(nested, name)
            nested = getattr(group, "driven_mode", None)
            if nested is not None and hasattr(nested, name):
                return getattr(nested, name)
        group = getattr(client, legacy_group, None)
        if group is not None and hasattr(group, name):
            return getattr(group, name)
        raise RuntimeError(f"The current MultiPyVu version lacks the mode enum {name}")

    def set_temperature(
        self, target_k: float, rate_k_min: float, approach_code: int
    ) -> dict[str, object]:
        with self.lock:
            if self.client is None:
                raise RuntimeError("PPMS MultiVu is not connected")
            current_k, _status = self.client.get_temperature()
            target_k, rate_k_min = validate_ppms_temperature_command(
                target_k, rate_k_min, float(current_k)
            )
            approach_name = "fast_settle" if int(approach_code) == 0 else "no_overshoot"
            approach = self._enum_member(
                self.client, "temperature", "temp_approach_mode", approach_name
            )
            self.client.set_temperature(target_k, float(rate_k_min), approach)
            return self.read_environment()

    def set_field(
        self,
        target_oe: float,
        rate_oe_s: float,
        approach_code: int,
        mode_code: int,
    ) -> dict[str, object]:
        target_oe, rate_oe_s = validate_ppms_field_command(target_oe, rate_oe_s)
        approach_names = {0: "linear", 1: "no_overshoot", 2: "oscillate"}
        mode_names = {0: "persistent", 1: "driven"}
        try:
            approach_name = approach_names[int(approach_code)]
            mode_name = mode_names[int(mode_code)]
        except KeyError as error:
            raise ValueError("PPMS field approach/mode parameters are invalid") from error
        with self.lock:
            if self.client is None:
                raise RuntimeError("PPMS MultiVu is not connected")
            approach = self._enum_member(
                self.client, "field", "field_approach_mode", approach_name
            )
            mode = self._enum_member(
                self.client, "field", "field_driven_mode", mode_name
            )
            self.client.set_field(target_oe, rate_oe_s, approach, mode)
            return self.read_environment()

    def disconnect(self) -> None:
        with self.lock:
            client = self.client
            self.client = None
            self.host = ""
            self.port = 0
            if client is None:
                return
            # Close only this client.  Never call close_server(), and never
            # alter an in-progress PPMS temperature or field ramp on exit.
            client.close_client()
            self.logger("PPMS MultiVu client disconnected (current setpoints unchanged)")


__all__ = ["PPMSMultiVuReadbackController"]
