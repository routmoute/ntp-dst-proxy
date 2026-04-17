import socket
import struct
import time
import ntplib
import os
import signal
import sys
import logging
from datetime import datetime
import zoneinfo
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Load configuration from environment variables
TZ_NAME = os.getenv("TZ", "Europe/Paris")
NTP_SERVERS_STR = os.getenv("NTP_SERVERS", "0.pool.ntp.org,1.pool.ntp.org")
NTP_SERVERS = [s.strip() for s in NTP_SERVERS_STR.split(",") if s.strip()]

# Validate NTP_SERVERS
if not NTP_SERVERS:
    logger.error("No valid NTP servers provided")
    sys.exit(1)

try:
    TZ = zoneinfo.ZoneInfo(TZ_NAME)
    logger.info(f"Timezone: {TZ_NAME}")
    logger.info(f"NTP Servers: {', '.join(NTP_SERVERS)}")
except Exception as e:
    logger.error(f"Invalid timezone '{TZ_NAME}': {e}")
    raise

cache_lock = threading.Lock()
last_ntp_time = None
last_sync_monotonic = None
last_dst_offset = None
last_dst_update = None


def get_dst_offset():
    """Get DST offset with caching (updated every 60 seconds)"""
    global last_dst_offset, last_dst_update
    
    current_time = time.time()
    with cache_lock:
        if last_dst_update is None or (current_time - last_dst_update) > 60:
            now = datetime.now(TZ)
            last_dst_offset = now.utcoffset().total_seconds()
            last_dst_update = current_time
        return last_dst_offset


def sync_time():
    global last_ntp_time, last_sync_monotonic

    client = ntplib.NTPClient()

    # Perform initial sync with retry (up to 3 times)
    initial_sync_done = False
    for attempt in range(3):
        for server in NTP_SERVERS:
            try:
                response = client.request(server, version=3, timeout=5)
                with cache_lock:
                    last_ntp_time = response.tx_time
                    last_sync_monotonic = time.monotonic()
                logger.info(f"Initial sync OK via {server}")
                initial_sync_done = True
                break
            except Exception as e:
                logger.warning(f"Initial sync attempt {attempt + 1}/3 FAIL {server}: {e}")
        
        if initial_sync_done:
            break
        if attempt < 2:
            time.sleep(2)  # wait 2 seconds before retry
    
    if not initial_sync_done:
        logger.warning("Initial sync failed after 3 attempts, using system time as fallback")

    # Continuous resync loop
    while True:
        for server in NTP_SERVERS:
            try:
                response = client.request(server, version=3, timeout=5)
                with cache_lock:
                    last_ntp_time = response.tx_time
                    last_sync_monotonic = time.monotonic()
                logger.info(f"Sync OK via {server}")
                break
            except Exception as e:
                logger.warning(f"Sync FAIL {server}: {e}")

        time.sleep(60)  # resync every 60s


def get_current_time():
    with cache_lock:
        if last_ntp_time is None:
            # complete fallback
            return time.time()

        elapsed = time.monotonic() - last_sync_monotonic
        return last_ntp_time + elapsed


def build_response(request, fake_time):
    LI_VN_MODE = (0 << 6) | (4 << 3) | 4
    stratum = 2
    poll = 0
    precision = -20

    root_delay = 0
    root_dispersion = 0
    ref_id = b'LOCL'

    def to_ntp(ts):
        """Convert Unix timestamp to NTP timestamp (seconds + fraction)"""
        seconds = int(ts) + 2208988800
        # Extract fractional part and convert to 32-bit fraction
        fraction = int((ts % 1) * (2**32))
        return seconds, fraction

    unpacked = struct.unpack("!12I", request)
    # Extract Transmit Timestamp from request (indices 10-11) - this becomes Origin in response
    origin_ts_int = unpacked[10]
    origin_ts_frac = unpacked[11]

    # Convert fake_time (with DST offset) to proper NTP format
    ref_sec, ref_frac = to_ntp(fake_time)
    recv_sec, recv_frac = to_ntp(fake_time)
    xmit_sec, xmit_frac = to_ntp(fake_time)

    packet = struct.pack(
        "!BBBbII4sIIIIIIII",
        LI_VN_MODE,
        stratum,
        poll,
        precision,
        root_delay,
        root_dispersion,
        ref_id,
        ref_sec, ref_frac,              # Reference Timestamp
        origin_ts_int, origin_ts_frac,  # Origin Timestamp (from client)
        recv_sec, recv_frac,            # Receive Timestamp
        xmit_sec, xmit_frac             # Transmit Timestamp
    )

    return packet


def serve():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 123))

    logger.info("NTP proxy started (stable + DST + cache)")

    def shutdown_handler(signum, frame):
        logger.info("Received signal, closing gracefully...")
        sock.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        while True:
            try:
                data, addr = sock.recvfrom(1024)

                # Validate packet size (NTP packets are 48 bytes minimum)
                if len(data) < 48:
                    logger.warning(f"Invalid packet size from {addr}: {len(data)} bytes")
                    continue

                current_time = get_current_time()
                offset = get_dst_offset()
                fake_time = current_time + offset

                # Build response with fake_time (UTC + DST offset)
                response = build_response(data, fake_time)
                sock.sendto(response, addr)
            except struct.error as e:
                logger.warning(f"Packet parsing error from {addr}: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                continue
    finally:
        sock.close()
        logger.info("Socket closed")


# NTP sync thread
threading.Thread(target=sync_time, daemon=True).start()

# Start server
serve()
