# ntp-dst-proxy

ntp-dst-proxy is a lightweight and resilient NTP proxy designed for legacy or embedded devices that lack proper timezone and DST support.

Instead of returning UTC like a standard NTP server, it dynamically adjusts time based on a configured timezone (e.g. Europe/Paris), including automatic Daylight Saving Time transitions.

Features:
- Automatic DST handling using system timezone
- Smart caching with offline fallback
- Continuous time reconstruction (no restart required)
- Multi-server NTP synchronization
- Docker support for easy deployment

Use case:
Ideal for IP cameras, DVRs, and IoT devices that cannot correctly handle timezones or DST.

⚠️ This implementation intentionally deviates from the NTP standard by serving localized time instead of UTC.

## Quick Start

```bash
docker run -d -p 123:123/udp routmoute/ntp-dst-proxy
```

Your NTP server is now running and serving time in Europe/Paris timezone (default).

## Configuration

You can customize the proxy using environment variables:

- **`TZ`** (default: `Europe/Paris`): System timezone as IANA timezone identifier (e.g., `America/New_York`, `Asia/Tokyo`)
- **`NTP_SERVERS`** (default: `0.pool.ntp.org,1.pool.ntp.org`): Comma-separated list of NTP servers to sync with

### Example usage:

```bash
docker run -d -p 123:123/udp \
  -e TZ="America/New_York" \
  -e NTP_SERVERS="time.google.com,time.cloudflare.com" \
  routmoute/ntp-dst-proxy
```

### Docker Compose:

```yaml
services:
  ntp-proxy:
    image: routmoute/ntp-dst-proxy
    ports:
      - "123:123/udp"
    environment:
      TZ: "Europe/Paris"
      NTP_SERVERS: "0.pool.ntp.org,1.pool.ntp.org"
    restart: unless-stopped
```

## Troubleshooting

### NTP sync fails at startup

If you see repeated `Initial sync FAIL` messages:
- Check your network connectivity
- Verify the NTP servers are accessible: `docker exec <container> nc -u <server> 123`
- Try different NTP servers (e.g., `time.google.com`)
- The proxy will continue working with system time as fallback

### Wrong time on clients

- Verify the `TZ` environment variable is set correctly (must be a valid IANA timezone)
- Check the server logs: `docker logs <container>`
- Ensure clients are using the correct timezone offset

### Invalid timezone error

The proxy won't start if an invalid timezone is provided. Use one from the [IANA timezone database](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones):
```bash
docker run -e TZ="America/New_York" ...
```

## Limitations

- **Non-standard behavior**: This proxy intentionally deviates from NTP standard (RFC 5905) by serving localized time instead of UTC
- **Timezone-dependent**: Time is adjusted based on the configured timezone and DST rules
- **Single-threaded handling**: Each request is processed sequentially (UDP socket)
- **DST calculation**: DST transitions are calculated based on the system timezone database (tzdata)
- **Cached offsets**: DST offset is cached for 60 seconds to improve performance
- **Not suitable for**: High-precision timekeeping (stratum is set to 2, not ideal for critical systems)
