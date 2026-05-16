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

import sys
import asyncio
import configparser
import websockets

config = configparser.ConfigParser()
config.read('/usr/local/etc/petitban.conf')

DAEMON_ADDR = config['DEFAULT'].get('LISTEN_ADDR',        '127.0.0.1')
DAEMON_PORT = config['DEFAULT'].get('LISTEN_PORT',        8765)
IPFW_TABLE  = config['DEFAULT'].get('DEFAULT_IPFW_TABLE', '80')

async def send(tbl,act,ip,comm):
    uri = f"ws://{DAEMON_ADDR}:{DAEMON_PORT}"
    async with websockets.connect(uri) as ws:
        await ws.send(f'{tbl} {act} {ip} "{comm}"')

if __name__ == "__main__":
    args = sys.argv[1:]
    comm = "MANUAL"
    n    = int(IPFW_TABLE, 10)

    if len(args) <= 1 :
        print("Usage: petitban_send.py [TABLE] <add|del> <IP> [COMMENT]")
        sys.exit(1)

    try:
        n   = int(args[0], 10)  ## 数値にパースできるか見るだけ
        tbl = args[0]
        act = args[1]
        ip  = args[2]
        if len(args) >= 4 :
            comm = args[3]

    except ValueError:
        tbl = IPFW_TABLE  ## 数値じゃなければ省略されていたと判断
        act = args[0]
        ip  = args[1]
        if len(args) >= 3 :
            comm = args[2]

    if (0 > n) or (n > 65535) :
        print(f'bad TABLE number: {n}')
        sys.exit(1)
  
    asyncio.run(send(tbl,act,ip,comm))
