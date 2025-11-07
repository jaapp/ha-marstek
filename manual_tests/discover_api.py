#!/usr/bin/env python3
"""Systematic API endpoint discovery for Marstek devices.

This script attempts to discover undocumented API endpoints by systematically
testing various method names and parameter combinations.

Usage:
  python3 discover_api.py                    # Auto-discover device
  python3 discover_api.py 192.168.7.101      # Test specific IP
  python3 discover_api.py --verbose          # Show all attempts
  python3 discover_api.py --delay 2.0        # Increase delay between requests
"""

import argparse
import json
import socket
import sys
import time
from dataclasses import dataclass
from typing import Any, Optional, TextIO
from datetime import datetime
from pathlib import Path

# Configuration
DEFAULT_PORT = 30000
DISCOVERY_TIMEOUT = 9
COMMAND_TIMEOUT = 15
MAX_RETRIES = 3
RATE_LIMIT_DELAY = 15.0  # Matches production integration; override with --delay for faster probing
# Retry backoff uses the delay multiplier (1x, 3x, ...), so longer delays probe more gently.

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "discover_api.log"
LOG_HANDLE: Optional[TextIO] = None
LOG_AVAILABLE = False


def log(message: str = "", *, flush: bool = False, console: bool = True) -> None:
    """Log message to console and log file."""
    if console:
        print(message, flush=flush)
    if LOG_HANDLE:
        LOG_HANDLE.write(message + "\n")
        LOG_HANDLE.flush()


def start_log_session(session_label: str, delay: float) -> None:
    """Initialise logging for this script run."""
    global LOG_HANDLE, LOG_AVAILABLE

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        print(f"⚠️  Could not create log directory {LOG_DIR}: {err}")
        LOG_AVAILABLE = False
        return

    try:
        LOG_HANDLE = LOG_FILE.open("a", encoding="utf-8")
    except OSError as err:
        LOG_HANDLE = None
        print(f"⚠️  Could not open log file {LOG_FILE}: {err}")
        LOG_AVAILABLE = False
        return

    LOG_AVAILABLE = True
    timestamp = datetime.now().isoformat(timespec="seconds")
    header = [
        "=" * 80,
        f"{timestamp} | Session start: {session_label}",
        f"Rate limit: {delay}s",
    ]
    for line in header:
        log(line, console=False)


def end_log_session() -> None:
    """Close log file handle if open."""
    global LOG_HANDLE, LOG_AVAILABLE

    if LOG_HANDLE:
        LOG_HANDLE.write("Session end\n\n")
        LOG_HANDLE.flush()
        LOG_HANDLE.close()
        LOG_HANDLE = None
    LOG_AVAILABLE = False


@dataclass
class ApiResult:
    """Result of an API endpoint test."""
    method: str
    params: dict
    success: bool
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    result: Optional[dict] = None
    response_time: Optional[float] = None


# Candidate endpoints to test
ENDPOINT_CANDIDATES = [
    # Known working endpoint - sanity check
    ("ES.GetMode", {"id": 0}),  # Should succeed - validates tool is working

    # Most likely - ES component variants
    ("ES.GetConfig", {"id": 0}),
    ("ES.GetModeConfig", {"id": 0}),
    ("ES.GetManualConfig", {"id": 0}),
    ("ES.GetManualCfg", {"id": 0}),
    ("ES.GetSchedule", {"id": 0}),
    ("ES.GetSchedules", {"id": 0}),
    ("ES.GetTimeSchedule", {"id": 0}),
    ("ES.GetSettings", {"id": 0}),
    ("ES.GetConfiguration", {"id": 0}),
    ("ES.GetAllModes", {"id": 0}),
    ("ES.ListSchedules", {"id": 0}),
    ("ES.QuerySchedule", {"id": 0}),

    # ES.GetMode with additional parameters
    ("ES.GetMode", {"id": 0, "detailed": True}),
    ("ES.GetMode", {"id": 0, "include_config": True}),
    ("ES.GetMode", {"id": 0, "include_schedules": True}),
    ("ES.GetMode", {"id": 0, "mode": "Manual"}),

    # ES.GetMode with schedule slot parameter
    ("ES.GetMode", {"id": 0, "time_num": 0}),
    ("ES.GetMode", {"id": 0, "time_num": 1}),

    # Manual component
    ("Manual.GetStatus", {"id": 0}),
    ("Manual.GetConfig", {"id": 0}),
    ("Manual.GetSchedules", {"id": 0}),
    ("Manual.GetSchedule", {"id": 0}),
    ("Manual.GetSchedule", {"id": 0, "time_num": 0}),

    # Schedule component
    ("Schedule.GetStatus", {"id": 0}),
    ("Schedule.GetConfig", {"id": 0}),
    ("Schedule.GetAll", {"id": 0}),
    ("Schedule.List", {"id": 0}),

    # Other mode configs
    ("ES.GetAutoCfg", {"id": 0}),
    ("ES.GetAICfg", {"id": 0}),
    ("ES.GetPassiveCfg", {"id": 0}),

    # Alternative component names
    ("Config.GetManual", {"id": 0}),
    ("Config.GetSchedules", {"id": 0}),
    ("System.GetSchedules", {"id": 0}),
    ("Mode.GetConfig", {"id": 0}),
    ("Mode.GetManual", {"id": 0}),
]


class MarstekApiDiscovery:
    """Standalone UDP client for API endpoint discovery."""

    def __init__(self, host: str, port: int = DEFAULT_PORT, verbose: bool = False, delay: float = RATE_LIMIT_DELAY):
        self.host = host
        self.port = port
        self.verbose = verbose
        self.delay = delay
        self.sock: Optional[socket.socket] = None
        self.request_id = 0

    def connect(self):
        """Create UDP socket."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(COMMAND_TIMEOUT)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        try:
            # Bind to the same port the device expects (matches HA integration behaviour)
            self.sock.bind(("", self.port))
        except OSError as err:
            log(f"⚠️  Could not bind command socket to UDP port {self.port}: {err}")
            log("   This may prevent responses from being received.")
        else:
            local_port = self.sock.getsockname()[1]
            log(f"[Socket] Bound local UDP port {local_port}")

    def disconnect(self):
        """Close UDP socket."""
        if self.sock:
            self.sock.close()
            self.sock = None

    def send_command(self, method: str, params: dict, retries: int = MAX_RETRIES) -> ApiResult:
        """Send command with retry and backoff logic."""
        if not self.sock:
            raise RuntimeError("Socket is not connected. Call connect() first.")

        self.request_id += 1
        request = {
            "id": self.request_id,
            "method": method,
            "params": params,
        }

        start_time = time.time()
        last_error = None

        for attempt in range(1, retries + 1):
            try:
                # Send request
                message = json.dumps(request).encode('utf-8')
                self.sock.sendto(message, (self.host, self.port))

                # Receive response
                try:
                    data, _ = self.sock.recvfrom(65535)
                    response = json.loads(data.decode('utf-8'))
                    response_time = time.time() - start_time

                    # Check for error
                    if "error" in response:
                        error = response["error"]
                        return ApiResult(
                            method=method,
                            params=params,
                            success=False,
                            error_code=error.get("code"),
                            error_message=error.get("message"),
                            response_time=response_time,
                        )

                    # Success
                    return ApiResult(
                        method=method,
                        params=params,
                        success=True,
                        result=response.get("result"),
                        response_time=response_time,
                    )

                except socket.timeout:
                    last_error = f"Timeout (attempt {attempt}/{retries})"
                    if self.verbose:
                        log(f"  ⏱️  {last_error}")

                    # Delay before retry using configured multiplier
                    if attempt < retries:
                        multiplier = 1 if attempt == 1 else 3
                        backoff = self.delay * multiplier
                        if self.verbose:
                            log(f"  🔁 Retry in {backoff:.1f}s (multiplier x{multiplier})")
                        time.sleep(backoff)

            except Exception as e:
                last_error = str(e)
                if self.verbose:
                    log(f"  ❌ Error: {e}")

        # All retries failed
        response_time = time.time() - start_time
        return ApiResult(
            method=method,
            params=params,
            success=False,
            error_message=f"Failed after {retries} attempts: {last_error}",
            response_time=response_time,
        )

    def test_endpoint(self, method: str, params: dict) -> ApiResult:
        """Test a single endpoint."""
        result = self.send_command(method, params)

        # Rate limiting
        time.sleep(self.delay)

        return result

    def handshake(self) -> ApiResult:
        """Perform an initial handshake to validate connectivity."""
        log("[Handshake] Requesting device info...", flush=True)
        result = self.send_command("Marstek.GetDevice", {"ble_mac": "0"})
        if result.success and result.result:
            device = result.result.get("device", "Unknown")
            firmware = result.result.get("ver", "unknown")
            log(f"[Handshake] ✅ Device responded: {device} (firmware v{firmware})")
        else:
            log("[Handshake] ⚠️  Device did not respond to Marstek.GetDevice request")
            if result.error_message:
                log(f"[Handshake]     Error: {result.error_message}")
        log()
        return result


def get_broadcast_addresses() -> list[str]:
    """Get broadcast addresses for local networks."""
    import subprocess

    broadcast_addrs = []

    try:
        # Parse ifconfig to find network broadcast addresses
        result = subprocess.run(['ifconfig'], capture_output=True, text=True, timeout=2)

        for line in result.stdout.split('\n'):
            if '\tinet ' in line and 'broadcast' in line:
                parts = line.strip().split()
                if 'broadcast' in parts:
                    idx = parts.index('broadcast')
                    if idx + 1 < len(parts):
                        broadcast = parts[idx + 1]
                        # Skip loopback
                        if not broadcast.startswith('127.'):
                            broadcast_addrs.append(broadcast)
    except Exception:
        pass

    # Always include global broadcast as fallback
    if '255.255.255.255' not in broadcast_addrs:
        broadcast_addrs.append('255.255.255.255')

    return broadcast_addrs


def discover_device() -> Optional[str]:
    """Discover Marstek device on network."""
    log("🔍 Discovering Marstek devices...")

    broadcast_addrs = get_broadcast_addresses()
    log(f"Broadcasting to: {', '.join(broadcast_addrs)}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

    try:
        # Bind to Marstek discovery port so the device can respond to the expected port
        sock.bind(("", DEFAULT_PORT))
    except OSError as err:
        log(f"⚠️  Could not bind to UDP port {DEFAULT_PORT}: {err}")
        log("   Discovery responses might not be received.")

    sock.settimeout(2.0)  # 2-second timeout for receiving

    discovery_message = json.dumps({
        "id": 0,
        "method": "Marstek.GetDevice",
        "params": {"ble_mac": "0"}
    }).encode('utf-8')

    try:
        start = time.time()
        last_broadcast = 0

        # Broadcast repeatedly every 2 seconds during discovery window
        while time.time() - start < DISCOVERY_TIMEOUT:
            current_time = time.time()

            # Send broadcast every 2 seconds to all broadcast addresses
            if current_time - last_broadcast >= 2.0:
                for broadcast_addr in broadcast_addrs:
                    sock.sendto(discovery_message, (broadcast_addr, DEFAULT_PORT))
                last_broadcast = current_time

            # Try to receive responses
            try:
                data, addr = sock.recvfrom(65535)
                response = json.loads(data.decode('utf-8'))

                if "result" in response and "device" in response["result"]:
                    device = response["result"]
                    ip = device.get("ip", addr[0])
                    log(f"✅ Found {device['device']} at {ip}")
                    sock.close()
                    return ip

            except socket.timeout:
                # Normal - no response yet, continue broadcasting
                continue
            except Exception:
                continue

        # Wait 2 more seconds for delayed responses
        sock.settimeout(2.0)
        try:
            data, addr = sock.recvfrom(65535)
            response = json.loads(data.decode('utf-8'))

            if "result" in response and "device" in response["result"]:
                device = response["result"]
                ip = device.get("ip", addr[0])
                log(f"✅ Found {device['device']} at {ip}")
                sock.close()
                return ip
        except:
            pass

    finally:
        sock.close()

    return None


def test_all_endpoints(client: MarstekApiDiscovery):
    """Test all candidate endpoints."""
    log()
    log("=" * 80)
    log("API Endpoint Discovery")
    log("=" * 80)
    log(f"Target: {client.host}:{client.port}")
    log(f"Rate limit: {client.delay}s between requests")
    log(f"Testing {len(ENDPOINT_CANDIDATES)} endpoint candidates...")
    log("=" * 80)
    log()

    results = {
        "found": [],           # Working endpoints
        "exists": [],          # Exists but wrong params
        "not_found": [],       # Method not found
        "timeout": [],         # Timeouts
        "other_error": [],     # Other errors
    }

    total = len(ENDPOINT_CANDIDATES)
    max_wait = COMMAND_TIMEOUT * MAX_RETRIES
    multipliers: list[float] = []
    if MAX_RETRIES > 1:
        multipliers.append(1.0)
        if MAX_RETRIES > 2:
            multipliers.extend([3.0] * (MAX_RETRIES - 2))
    backoff_total = sum(multiplier * client.delay for multiplier in multipliers)
    max_wait_with_backoff = max_wait + backoff_total

    for idx, (method, params) in enumerate(ENDPOINT_CANDIDATES, 1):
        params_str = json.dumps(params) if params != {"id": 0} else ""
        label = f"{method}{' ' + params_str if params_str else ''}"

        if client.verbose:
            log(f"[{idx}/{total}] Testing {label}...", flush=True)
        else:
            log(f"[{idx}/{total}] Testing {label} (max wait ~{max_wait_with_backoff:.0f}s incl. backoff)", flush=True)

        result = client.test_endpoint(method, params)

        if result.success:
            results["found"].append(result)
            log(f"  🎉 FOUND! {method} -> Success!")
            log(f"     Result: {json.dumps(result.result, indent=2)}")

        elif result.error_code == -32601:
            # Method not found
            results["not_found"].append(result)
            log(f"  ❌ Not found: {method}")

        elif result.error_code == -32602:
            # Invalid params - METHOD EXISTS!
            results["exists"].append(result)
            log(f"  ⚠️  EXISTS but wrong params: {method}")
            log(f"     Error: {result.error_message}")

        elif result.error_code:
            # Other error code
            results["other_error"].append(result)
            log(f"  ⚠️  Error {result.error_code}: {method} - {result.error_message}")

        else:
            # Timeout or network error
            results["timeout"].append(result)
            log(f"  ⏱️  Timeout: {method} ({result.error_message or 'no response'})")

    return results


def print_summary(results: dict):
    """Print summary of discovery results."""
    log()
    log("=" * 80)
    log("DISCOVERY SUMMARY")
    log("=" * 80)
    log()

    if results["found"]:
        log(f"✅ WORKING ENDPOINTS ({len(results['found'])}):")
        for r in results["found"]:
            params_str = json.dumps(r.params) if r.params != {"id": 0} else ""
            log(f"   • {r.method}{' ' + params_str if params_str else ''}")
            log(f"     Response time: {r.response_time:.2f}s")
        log()

    if results["exists"]:
        log(f"⚠️  ENDPOINTS THAT EXIST BUT NEED DIFFERENT PARAMS ({len(results['exists'])}):")
        for r in results["exists"]:
            params_str = json.dumps(r.params)
            log(f"   • {r.method} (tried with {params_str})")
            log(f"     Error: {r.error_message}")
        log()

    if results["other_error"]:
        log(f"⚠️  OTHER ERRORS ({len(results['other_error'])}):")
        for r in results["other_error"]:
            log(f"   • {r.method}: Error {r.error_code} - {r.error_message}")
        log()

    log(f"❌ Not found: {len(results['not_found'])}")
    log(f"⏱️  Timeouts: {len(results['timeout'])}")
    log()

    total_tested = sum(len(v) for v in results.values())
    log(f"Total endpoints tested: {total_tested}")
    log("=" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Discover undocumented Marstek API endpoints"
    )
    parser.add_argument(
        "ip",
        nargs="?",
        help="Target device IP (default: auto-discover)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show all endpoint tests including failures",
    )
    parser.add_argument(
        "-d", "--delay",
        type=float,
        default=RATE_LIMIT_DELAY,
        help=f"Delay between requests in seconds (default: {RATE_LIMIT_DELAY})",
    )

    args = parser.parse_args()
    session_label = args.ip or "auto-discover"
    start_log_session(session_label, args.delay)

    # Get target IP
    target_ip = args.ip
    if not target_ip:
        target_ip = discover_device()
        if not target_ip:
            log("❌ No devices found! Please specify IP address.")
            if LOG_AVAILABLE:
                log(f"📝 Detailed log saved to {LOG_FILE}")
            else:
                log("ℹ️ File logging unavailable for this run.")
            end_log_session()
            sys.exit(1)

    log()
    log(f"🎯 Target device: {target_ip}")
    log()
    log(f"[Session] Using target device: {target_ip}")
    log(f"[Session] Rate limit: {args.delay}s")

    # Create client
    client: Optional[MarstekApiDiscovery] = MarstekApiDiscovery(target_ip, verbose=args.verbose, delay=args.delay)

    try:
        client.connect()
        handshake_result = client.handshake()
        if not handshake_result.success:
            log("⚠️  Skipping endpoint sweep because handshake failed.")
            log("   Check network/firewall settings or increase --delay.")
            if LOG_AVAILABLE:
                log(f"📝 Detailed log saved to {LOG_FILE}")
            else:
                log("ℹ️ File logging unavailable for this run.")
            return
        results = test_all_endpoints(client)
        print_summary(results)
        if LOG_AVAILABLE:
            log(f"📝 Detailed log saved to {LOG_FILE}")
        else:
            log("ℹ️ File logging unavailable for this run.")

    except KeyboardInterrupt:
        log("\n\n⚠️  Discovery interrupted by user")
        sys.exit(0)

    finally:
        if client:
            client.disconnect()
        end_log_session()


if __name__ == "__main__":
    main()
