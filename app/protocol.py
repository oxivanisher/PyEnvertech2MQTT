"""
Envertech local TCP protocol implementation.
Based on https://github.com/Kaiserdragon2/envertech_local_python
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

CONTROL_CODE_REQUEST = 4215   # 0x1077 — data request
CONTROL_CODE_BREAK = 4161    # 0x1041 — graceful disconnect
CONTROL_CODE_RESPONSE = 4177  # 0x1051 — data response
CONTROL_CODE_ACK = 4102      # 0x1006 — command acknowledged

PANEL_DATA_SIZE = 32
HEADER_SIZE = 20
FOOTER_SIZE = 2


def _check_cs(data: bytearray) -> int:
    return (sum(data) + 85) & 0xFF


def _to_int16(b1: int, b2: int) -> int:
    return b1 * 256 + b2


def _to_int32(b1: int, b2: int, b3: int, b4: int) -> int:
    return (b1 << 24) + (b2 << 16) + (b3 << 8) + b4


def _parse_panel(data: list[int], base: int) -> dict | None:
    try:
        return {
            "mi_sn": "".join(f"{data[base + i]:02x}" for i in range(4)),
            "input_voltage": round(_to_int16(data[base + 6], data[base + 7]) * 64 / 32768, 2),
            "power": round(_to_int16(data[base + 8], data[base + 9]) * 512 / 32768, 2),
            "energy": round(_to_int32(data[base + 10], data[base + 11], data[base + 12], data[base + 13]) * 4 / 32768, 2),
            "temperature": round(_to_int16(data[base + 14], data[base + 15]) * 256 / 32768 - 40, 2),
            "grid_voltage": round(_to_int16(data[base + 16], data[base + 17]) * 512 / 32768, 2),
            "frequency": round(_to_int16(data[base + 18], data[base + 19]) * 128 / 32768, 2),
        }
    except IndexError:
        return None


def _build_command(sn_hex: str, control_code: int, padding: int = 0, payload: bytes = b"") -> bytes:
    if len(sn_hex) != 8:
        logger.error(f"Serial number must be exactly 8 hex characters, got: {sn_hex!r}")
        return b""
    data = bytearray()
    data.append(0x68)
    data.append(0x00)  # length high — filled in below
    data.append(0x00)  # length low  — filled in below
    data.append(0x68)
    data += control_code.to_bytes(2, "big")
    data += bytes.fromhex(sn_hex)
    data += payload
    data += bytes(padding)
    total_length = len(data) + 2  # +1 checksum, +1 end byte
    data[1] = (total_length >> 8) & 0xFF
    data[2] = total_length & 0xFF
    data.append(_check_cs(data))
    data.append(0x16)
    return bytes(data)


def build_request(sn_hex: str) -> bytes:
    return _build_command(sn_hex, CONTROL_CODE_REQUEST, padding=20)


def build_break(sn_hex: str) -> bytes:
    return _build_command(sn_hex, CONTROL_CODE_BREAK, padding=10)


def parse_response(raw: list[int]) -> tuple[dict, int | None]:
    if not raw or len(raw) < HEADER_SIZE + FOOTER_SIZE:
        return {}, None

    control_code = int.from_bytes(bytes(raw[4:6]), "big")
    if control_code != CONTROL_CODE_RESPONSE:
        logger.debug(f"Unexpected control code: {control_code:#06x}")
        return {}, None

    n_panels = (len(raw) - HEADER_SIZE - FOOTER_SIZE) // PANEL_DATA_SIZE
    data: dict = {}

    for i in range(n_panels):
        panel = _parse_panel(raw, HEADER_SIZE + i * PANEL_DATA_SIZE)
        if panel:
            data[f"panel_{i}"] = panel

    panels = [v for v in data.values() if isinstance(v, dict)]
    data["total_power"] = round(sum(p.get("power", 0) for p in panels), 2)
    data["total_energy"] = round(sum(p.get("energy", 0) for p in panels), 2)
    data["panel_count"] = n_panels
    data["firmware_version"] = f"{raw[10]}/{raw[12]}"

    return data, n_panels


class InverterClient:
    def __init__(self, ip: str, port: int, sn: str):
        self.ip = ip
        self.port = port
        self.sn = sn
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def _connect(self, timeout: float = 10.0):
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.ip, self.port),
            timeout=timeout,
        )
        logger.debug(f"Connected to {self.ip}:{self.port}")

    async def _disconnect(self):
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

    async def _send(self, payload: bytes):
        if self._writer is None:
            await self._connect()
        self._writer.write(payload)
        await self._writer.drain()

    async def _receive(self, timeout: float = 5.0) -> list[int] | None:
        try:
            raw = await asyncio.wait_for(self._reader.read(1024), timeout=timeout)
            return list(raw)
        except asyncio.TimeoutError:
            return None

    async def fetch(self, retries: int = 5) -> tuple[dict, int | None]:
        """Connect, request data, parse and return; always disconnects cleanly."""
        try:
            await self._send(build_request(self.sn))
            for attempt in range(retries):
                raw = await self._receive()
                if raw:
                    data, n_panels = parse_response(raw)
                    if data:
                        return data, n_panels
                logger.debug(f"Retry {attempt + 1}/{retries} for {self.ip}")
        finally:
            try:
                await self._send(build_break(self.sn))
            except Exception:
                pass
            await self._disconnect()
        return {}, None
