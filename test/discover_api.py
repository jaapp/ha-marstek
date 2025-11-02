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
from typing import Any, Optional

# Configuration
DEFAULT_PORT = 30000
DISCOVERY_TIMEOUT = 9
COMMAND_TIMEOUT = 15
MAX_RETRIES = 3
BACKOFF_BASE = 1.5
BACKOFF_FACTOR = 2.0
BACKOFF_MAX = 12.0
RATE_LIMIT_DELAY = 60.0  # Delay between API calls - Marstek is unreliable, needs long delays


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

    def disconnect(self):
        """Close UDP socket."""
        if self.sock:
            self.sock.close()
            self.sock = None

    def send_command(self, method: str, params: dict, retries: int = MAX_RETRIES) -> ApiResult:
        """Send command with retry and backoff logic."""
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
                        print(f"  ⏱️  {last_error}")

                    # Exponential backoff before retry
                    if attempt < retries:
                        backoff = min(BACKOFF_BASE * (BACKOFF_FACTOR ** (attempt - 1)), BACKOFF_MAX)
                        time.sleep(backoff)

            except Exception as e:
                last_error = str(e)
                if self.verbose:
                    print(f"  ❌ Error: {e}")

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


def discover_device() -> Optional[str]:
    """Discover Marstek device on network."""
    print("🔍 Discovering Marstek devices...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(DISCOVERY_TIMEOUT)

    discovery_message = json.dumps({
        "id": 0,
        "method": "Marstek.GetDevice",
        "params": {"ble_mac": "0"}
    }).encode('utf-8')

    try:
        sock.sendto(discovery_message, ('<broadcast>', DEFAULT_PORT))

        start = time.time()
        while time.time() - start < DISCOVERY_TIMEOUT:
            try:
                data, addr = sock.recvfrom(65535)
                response = json.loads(data.decode('utf-8'))

                if "result" in response and "device" in response["result"]:
                    device = response["result"]
                    ip = device.get("ip", addr[0])
                    print(f"✅ Found {device['device']} at {ip}")
                    sock.close()
                    return ip

            except socket.timeout:
                break
            except Exception:
                continue

    finally:
        sock.close()

    return None


def test_all_endpoints(client: MarstekApiDiscovery):
    """Test all candidate endpoints."""
    print()
    print("=" * 80)
    print("API Endpoint Discovery")
    print("=" * 80)
    print(f"Target: {client.host}:{client.port}")
    print(f"Rate limit: {client.delay}s between requests")
    print(f"Testing {len(ENDPOINT_CANDIDATES)} endpoint candidates...")
    print("=" * 80)
    print()

    results = {
        "found": [],           # Working endpoints
        "exists": [],          # Exists but wrong params
        "not_found": [],       # Method not found
        "timeout": [],         # Timeouts
        "other_error": [],     # Other errors
    }

    for idx, (method, params) in enumerate(ENDPOINT_CANDIDATES, 1):
        params_str = json.dumps(params) if params != {"id": 0} else ""

        if client.verbose:
            print(f"[{idx}/{len(ENDPOINT_CANDIDATES)}] Testing {method}{' ' + params_str if params_str else ''}...")
        else:
            # Progress indicator without verbose
            if idx % 5 == 0:
                print(f"  Progress: {idx}/{len(ENDPOINT_CANDIDATES)}...")

        result = client.test_endpoint(method, params)

        if result.success:
            results["found"].append(result)
            print(f"  🎉 FOUND! {method} -> Success!")
            print(f"     Result: {json.dumps(result.result, indent=2)}")

        elif result.error_code == -32601:
            # Method not found
            results["not_found"].append(result)
            if client.verbose:
                print(f"  ❌ Not found: {method}")

        elif result.error_code == -32602:
            # Invalid params - METHOD EXISTS!
            results["exists"].append(result)
            print(f"  ⚠️  EXISTS but wrong params: {method}")
            print(f"     Error: {result.error_message}")

        elif result.error_code:
            # Other error code
            results["other_error"].append(result)
            print(f"  ⚠️  Error {result.error_code}: {method} - {result.error_message}")

        else:
            # Timeout or network error
            results["timeout"].append(result)
            if client.verbose:
                print(f"  ⏱️  Timeout: {method}")

    return results


def print_summary(results: dict):
    """Print summary of discovery results."""
    print()
    print("=" * 80)
    print("DISCOVERY SUMMARY")
    print("=" * 80)
    print()

    if results["found"]:
        print(f"✅ WORKING ENDPOINTS ({len(results['found'])}):")
        for r in results["found"]:
            params_str = json.dumps(r.params) if r.params != {"id": 0} else ""
            print(f"   • {r.method}{' ' + params_str if params_str else ''}")
            print(f"     Response time: {r.response_time:.2f}s")
        print()

    if results["exists"]:
        print(f"⚠️  ENDPOINTS THAT EXIST BUT NEED DIFFERENT PARAMS ({len(results['exists'])}):")
        for r in results["exists"]:
            params_str = json.dumps(r.params)
            print(f"   • {r.method} (tried with {params_str})")
            print(f"     Error: {r.error_message}")
        print()

    if results["other_error"]:
        print(f"⚠️  OTHER ERRORS ({len(results['other_error'])}):")
        for r in results["other_error"]:
            print(f"   • {r.method}: Error {r.error_code} - {r.error_message}")
        print()

    print(f"❌ Not found: {len(results['not_found'])}")
    print(f"⏱️  Timeouts: {len(results['timeout'])}")
    print()

    total_tested = sum(len(v) for v in results.values())
    print(f"Total endpoints tested: {total_tested}")
    print("=" * 80)


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

    # Get target IP
    target_ip = args.ip
    if not target_ip:
        target_ip = discover_device()
        if not target_ip:
            print("❌ No devices found! Please specify IP address.")
            sys.exit(1)

    print()
    print(f"🎯 Target device: {target_ip}")
    print()

    # Create client
    client = MarstekApiDiscovery(target_ip, verbose=args.verbose, delay=args.delay)

    try:
        client.connect()
        results = test_all_endpoints(client)
        print_summary(results)

    except KeyboardInterrupt:
        print("\n\n⚠️  Discovery interrupted by user")
        sys.exit(0)

    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
