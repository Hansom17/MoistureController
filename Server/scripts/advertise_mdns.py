#!/usr/bin/env python3
"""Advertise the API on the local network (Server/specs.md Part A §13.4, App/specs.md Part A §6.4).

  pip install zeroconf
  python Server/scripts/advertise_mdns.py            # port 8000
  MC_INSTANCE_ID=my-pi MC_AUTH_MODE=dev python Server/scripts/advertise_mdns.py

Runs on the host (or with network_mode: host): multicast does not leave a
Docker bridge network.
"""

import os
import socket
import time

from zeroconf import IPVersion, ServiceInfo, Zeroconf

SERVICE_TYPE = "_moisture-api._tcp.local."


def local_addresses() -> list[bytes]:
    """IPv4 addresses of this host that a phone on the LAN could reach."""
    addresses: set[str] = set()
    try:
        # UDP connect sends nothing; it only picks the outbound interface.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            addresses.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return [socket.inet_aton(a) for a in sorted(addresses) if not a.startswith("127.")]


def build_info() -> ServiceInfo:
    hostname = socket.gethostname().split(".")[0]
    port = int(os.environ.get("MC_API_PORT", "8000"))
    return ServiceInfo(
        SERVICE_TYPE,
        f"Moisture API ({hostname}).{SERVICE_TYPE}",
        port=port,
        addresses=local_addresses(),
        server=f"{hostname}.local.",
        properties={
            "v": "1",
            "api": "/api/v1",
            "auth": "dev" if os.environ.get("MC_AUTH_MODE", "firebase") == "dev" else "firebase",
            "id": os.environ.get("MC_INSTANCE_ID", "mc-local"),
        },
    )


def main() -> None:
    info = build_info()
    zc = Zeroconf(ip_version=IPVersion.V4Only)
    zc.register_service(info)
    print(f"advertising {info.name} on port {info.port} "
          f"({', '.join(socket.inet_ntoa(a) for a in info.addresses)})", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        zc.unregister_service(info)
        zc.close()


if __name__ == "__main__":
    main()
