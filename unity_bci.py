"""Send the existing BCI protocol to the native Unity simulator.

From WSL NAT: python unity_bci.py forward --host windows
Unity must be started with --bci-remote for packets from another host.
"""
import argparse
import json
import socket
import struct
from pathlib import Path

COMMANDS = ('up', 'down', 'forward', 'rotate_right', 'stop')


def resolve_host(host):
    if host != 'windows':
        return host
    # WSL NAT exposes the Windows host as the default gateway. Mirrored WSL
    # networking may instead use --host 127.0.0.1; do not change network settings.
    try:
        for line in Path('/proc/net/route').read_text().splitlines()[1:]:
            fields = line.split()
            if fields[1] == '00000000' and int(fields[2], 16):
                return socket.inet_ntoa(struct.pack('<I', int(fields[2], 16)))
    except (OSError, ValueError, IndexError) as exc:
        raise RuntimeError('Cannot determine Windows host; pass --host IP_ADDRESS') from exc
    raise RuntimeError('No default gateway; pass --host IP_ADDRESS')


def send(command, host='127.0.0.1', port=9001, check=False):
    if command not in COMMANDS:
        raise ValueError('Unknown BCI command')
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        destination = (socket.gethostbyname(resolve_host(host)), port)
        sock.connect(destination)
        sock.send(json.dumps({'cmd': command}).encode())
        if check:
            sock.settimeout(3)
            return json.loads(sock.recv(256)).get('accepted') is True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=COMMANDS)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=9001)
    parser.add_argument('--check', action='store_true', help='wait for Unity acknowledgement')
    args = parser.parse_args()
    try:
        accepted = send(args.command, args.host, args.port, args.check)
    except OSError as exc:
        raise SystemExit(f'No Unity acknowledgement: {exc}. Check that TALON is running, '
                         'uses --bci-remote, and Windows Firewall permits this application.') from exc
    if args.check:
        print('Unity acknowledgement:', accepted)
        if not accepted:
            raise SystemExit('Unity received the command but BCI is disarmed or command is invalid')
    print(f'BCI {args.command} -> {resolve_host(args.host)}:{args.port}')
