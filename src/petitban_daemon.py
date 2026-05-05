#!/usr/local/bin/python3.11
#
# Copyright (c) 2026, k896951
# All rights reserved.
# See must LICENSE file.
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
VERSION     = "1.1"
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

def run_ipfw(cmd):
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True
        )
        return (0, result.stdout, result.stderr) # 正常に戻るのは戻り値ゼロの時だけだからゼロ直接でも問題がないっちゃぁ問題がない

    except subprocess.CalledProcessError as e:
        return (e.returncode, e.stdout, e.stderr)

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
                    # 同じIPアドレスの追加を連続実行しない
                    if LAST_ADD_IP == ip:
                        continue

                    LAST_ADD_IP = ip
                    rc, out, err = run_ipfw([IPFWCMD, "table", tbl, "add", ip])
                    if rc == 0:
                        log_syslog(f"Added to table {tbl}: {ip} ,{comment}")

                    elif rc == 71:
                        pass   # 既に存在 → ログを出さずに成功扱い

                    else:
                        LAST_ADD_IP = None
                        log_syslog(f"Error adding {ip} to table {tbl}: rc={rc}, stderr={err.strip()}" )

                case "DEL":
                    rc, out, err = run_ipfw([IPFWCMD, "table", tbl, "delete", ip])
                    if rc == 0:
                        log_syslog(f"Deleted from table {tbl}: {ip} ,{comment}")

                    elif rc == 71:
                        log_syslog(f"Not found in table {tbl}: {ip} ,{comment}")

                    else:
                        log_syslog(f"Error deleting {ip} from table {tbl}: rc={rc}, stderr={err.strip()}")

                    LAST_ADD_IP = None

                case _:
                    log_syslog(f"bad instruction:{words}")

        except Exception as e:
            ##print(f"[{DAEMONNAME}] Error: {e}")
            log_syslog(f"Error: {e}")

            try:
                await websocket.send(f"ERROR: {e}")
            except (ConnectionClosedOK, ConnectionClosedError):
                pass

def handle_sigterm(signum, frame):
    log_syslog(f"Shutting down {DAEMONNAME} {VERSION} daemon (SIGTERM received)")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

async def main():
    log_syslog(f"{DAEMONNAME} {VERSION} daemon started on addr ws://{LISTEN_ADDR}:{LISTEN_PORT}")
    async with websockets.serve(handler, LISTEN_ADDR, LISTEN_PORT):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())

