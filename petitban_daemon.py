#!/usr/local/bin/python3.11
#
# Note:
#   Ubuntu/Debian では /usr/bin/env python が有効だが、
#   FreeBSD (pkg/ports) では python コマンドが提供されないため失敗する。
#   Apache piped logger は PATH が空に近いので、絶対パス指定が必須。

import asyncio
import websockets
import subprocess
import shlex
import signal
import sys
import configparser
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

DAEMONNAME  = "petitban"
LAST_ADD_IP = None

config = configparser.ConfigParser()
config.read('/usr/local/etc/petitban.conf')
LISTEN_ADDR = config['DEFAULT'].get('LISTEN_ADDR', '127.0.0.1')
LISTEN_PORT = config['DEFAULT'].getint('LISTEN_PORT', 8765)
IPFWCMD     = config['DEFAULT'].get('IPFWCMD', "/sbin/ipfw")

def log_syslog(message):
    # logger コマンドで syslog に出力
    subprocess.run(
        ["logger", "-t", f"{DAEMONNAME}", message],
        check=False
    )

async def handler(websocket):
    global LAST_ADD_IP
    async for message in websocket:
        instruction = message.strip()
        words       = shlex.split(instruction)

        if len(words) != 4 :
            raise ValueError(f'bad instruction:{instruction}')

        tbl     = words[0].upper()
        act     = words[1].upper()
        ip      = words[2]
        comment = words[3]

        try:
            match act:
                case "ADD":
                    if LAST_ADD_IP == ip:
                        continue
                    subprocess.run(
                        [IPFWCMD, "table", tbl, "add", ip],
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    log_syslog(f"Added to table {tbl}: {ip} ,{comment}")
                    LAST_ADD_IP = ip

                case "DEL":
                    subprocess.run(
                        [IPFWCMD, "table", tbl, "delete", ip],
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    log_syslog(f"Deleted from table {tbl}: {ip} ,{comment}")

                case _:
                    log_syslog(f"bad instruction:{words}")

        except Exception as e:
            print(f"[{DAEMONNAME}] Error: {e}")
            log_syslog(f"Error: {e}")

            try:
                await websocket.send(f"ERROR: {e}")
            except (ConnectionClosedOK, ConnectionClosedError):
                pass

def handle_sigterm(signum, frame):
    log_syslog(f"Shutting down {DAEMONNAME} daemon (SIGTERM received)")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

async def main():
    log_syslog(f"{DAEMONNAME} daemon started on addr ws://{LISTEN_ADDR}:{LISTEN_PORT}")
    async with websockets.serve(handler, LISTEN_ADDR, LISTEN_PORT):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())

