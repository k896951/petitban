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
import uuid
import configparser
import ipaddress
import socket
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

DAEMONNAME  = "petitban"
VERSION     = "1.3"
LAST_ADD_IP = None

config = configparser.ConfigParser()
config.read('/usr/local/etc/petitban.conf')

INNER_LISTEN_ADDR   = config['DEFAULT'].get('LISTEN_ADDR', '127.0.0.1')
INNER_LISTEN_PORT   = config['DEFAULT'].getint('LISTEN_PORT', 8765)
IPFWCMD             = config['DEFAULT'].get('IPFWCMD', "/sbin/ipfw")
EXCLUDEIPS          = [h.strip() for h in config['DEFAULT'].get('EXCLUDEIPS', '').split(',') if h.strip()]

OUTER_LISTEN_ADDR   = config['DEFAULT'].get('OUTER_LISTEN_ADDR', '')
OUTER_LISTEN_PORT   = config['DEFAULT'].getint('OUTER_LISTEN_PORT', 8765)
OUTER_ALLOWED_HOSTS = [h.strip() for h in config['DEFAULT'].get('OUTER_ALLOWED_HOSTS','').split(',') if h.strip()]
RELAYHOSTS          = [h.strip() for h in config['DEFAULT'].get('RELAYHOSTS', '').split(',') if h.strip()]
RELAYPORT           = config['DEFAULT'].getint('RELAYPORT', 443)
RELAYPATH           = config['DEFAULT'].get('RELAYPATH', '/petitban-sync')
RELAYURLS           = [u.strip() for u in config['DEFAULT'].get('RELAYURLS', '').split(',') if u.strip()]

## 
## logging
##
def log_syslog(message):
    subprocess.run(
        ["logger", "-t", f"{DAEMONNAME}", message],
        check=False
    )

##
## normalize_host : hostname to IP
##
def normalize_host(host):
    h = host.strip()
    try:
        ipaddress.ip_address(h)  # if not IP, raise exception
        return h
    except ValueError:
        pass

    return socket.gethostbyname(h)

##
## normalize_hosts : hostname[] to IPs[]
##
def normalize_hosts(hosts):
    normalized = []
    for h in hosts:
        normalized.append( normalize_host(h) )

    return normalized

## 
## run ipfw command 
##
def run_ipfw(cmd):
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True
        )
        return (0, result.stdout, result.stderr) # return ZERO was safety end only. direct "0" coding is no problem.

    except subprocess.CalledProcessError as e:
        return (e.returncode, e.stdout, e.stderr)

## 
## relay request to remote hosts
##
async def relay_sync(tbl, act, ip):
    uid = str(uuid.uuid4())
    message = f"SYNC {uid} {tbl} {act} {ip}"

    for url in RELAYURLS:
        try:
            async with websockets.connect(url) as ws:
                await ws.send(message)
                log_syslog(f"SYNC sent: {tbl} {act} {ip} to {url} syncid={uid}")

        except Exception as e:
            log_syslog(f"{url} : {e}")

##
## Request from ws://OUTER_LISTEN_ADDR:OUTER_LISTN_PORT
##
async def process_sync(words, clientip):
    syncid = words[1]
    tbl    = words[2]
    act    = words[3].upper()
    ip     = words[4]

    ##log_syslog(f"SYNC received: {tbl} {act} {ip} from {clientip} syncid={syncid}")

    if ip in EXCLUDEIPS:
        return

    if act == "ADD":
        rc, out, err = run_ipfw([IPFWCMD, "table", tbl, "add", ip])
        if rc == 0:
            log_syslog(f"Added to table {tbl}: {ip} ,Request from {clientip} syncid={syncid}")
        elif rc != 71:
            log_syslog(f"Error adding : table={tbl}, ip={ip}, rc={rc}, stderr={err.strip()}")

    elif act == "DEL":
        rc, out, err = run_ipfw([IPFWCMD, "table", tbl, "delete", ip])
        if rc == 0:
            log_syslog(f"Deleted from table {tbl}: {ip} ,Request from {clientip} syncid={syncid}")
        elif rc != 71:
            log_syslog(f"Error deleting : table={tbl}, ip={ip}, rc={rc}, stderr={err.strip()}")

##
## Request from ws://INNER_LISTEN_ADDR:INNER_LISTEN_PORT
##
async def process_local(words):
    global LAST_ADD_IP

    tbl     = words[0]
    act     = words[1].upper()
    ip      = words[2]
    comment = words[3]

    if ip in EXCLUDEIPS:
        return

    if act == "ADD":
        if LAST_ADD_IP == ip:
            return

        LAST_ADD_IP = ip
        rc, out, err = run_ipfw([IPFWCMD, "table", tbl, "add", ip])
        if rc == 0:
            log_syslog(f"Added to table {tbl}: {ip} ,{comment}")
        elif rc != 71:
            LAST_ADD_IP = None
            log_syslog(f"Error adding : table={tbl}, ip={ip}, rc={rc}, stderr={err.strip()}")
            return

        if RELAYHOSTS:
            await relay_sync(tbl, "ADD", ip)

    elif act == "DEL":
        LAST_ADD_IP = None
        rc, out, err = run_ipfw([IPFWCMD, "table", tbl, "delete", ip])
        if rc == 0:
            log_syslog(f"Deleted from table {tbl}: {ip} ,{comment}")
        elif rc != 71:
            log_syslog(f"Error deleting : table={tbl}, ip={ip}, rc={rc}, stderr={err.strip()}")
            return

        if RELAYHOSTS:
            await relay_sync(tbl, "DEL", ip)

##
## Listener entry point(INNER entry handler)
##
async def handler_inner(websocket):
    async for message in websocket:
        instruction = message.strip()
        words = shlex.split(instruction)

        if (len(words) != 4) or ( words[1].upper() not in ("ADD", "DEL")) :
            log_syslog(f"bad instruction:{instruction}")
            continue

        await process_local(words)

##
## Listener entry point(OUTER entry handler)
##
async def handler_outer(websocket):
    async for message in websocket:
        instruction = message.strip()
        words = shlex.split(instruction)

        if (len(words) != 5) or (words[0].upper() != "SYNC") :
            log_syslog(f"bad SYNC instruction:{instruction}")
            continue
 
        xff = websocket.request.headers.get("X-Forwarded-For")
        clientip = xff.split(",")[0].strip() if xff else websocket.remote_address[0]

        if clientip not in OUTER_ALLOWED_HOSTS:
            log_syslog(f"Rejected not granted host: {clientip}")
            await websocket.close()
            return

        await process_sync(words, clientip)

def handle_sigterm(signum, frame):
    log_syslog(f"Shutting down {DAEMONNAME}-{VERSION} daemon (SIGTERM received)")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

async def main():
    global INNER_LISTEN_ADDR
    global OUTER_LISTEN_ADDR
    global OUTER_ALLOWED_HOSTS
    global RELAYURLS

    INNER_LISTEN_ADDR = normalize_host(INNER_LISTEN_ADDR)
    OUTER_LISTEN_ADDR = normalize_host(OUTER_LISTEN_ADDR)

    servers = [
        await websockets.serve(handler_inner, INNER_LISTEN_ADDR, INNER_LISTEN_PORT)
    ]
    message = f"{DAEMONNAME}-{VERSION} daemon started on addr ws://{INNER_LISTEN_ADDR}:{INNER_LISTEN_PORT}"

    if OUTER_LISTEN_ADDR != '' and (len(OUTER_ALLOWED_HOSTS) >= 1) :
        servers.append(
            await websockets.serve(handler_outer, OUTER_LISTEN_ADDR, OUTER_LISTEN_PORT)
        )
        message += f", ws://{OUTER_LISTEN_ADDR}:{OUTER_LISTEN_PORT}"

    log_syslog(message)

    if OUTER_LISTEN_ADDR != '' and (len(OUTER_ALLOWED_HOSTS) >= 1) :
        log_syslog(f"granted hosts: {OUTER_ALLOWED_HOSTS}")
        OUTER_ALLOWED_HOSTS = normalize_hosts(OUTER_ALLOWED_HOSTS)  #normalize to IP addr

    if len(RELAYURLS) > 0 :
        if len(RELAYHOSTS) > 0:
            log_syslog("RELAYHOSTS is deprecated and ignored because RELAYURLS is defined.")
    else :
        RELAYURLS = []
        for host in RELAYHOSTS :
            scheme = "ws" if ipaddress.ip_address(socket.gethostbyname(host)).is_private else "wss"
            RELAYURLS.append( f"{scheme}://{host}:{RELAYPORT}{RELAYPATH}" )

        if len(RELAYURLS) > 0:
            log_syslog("Converted RELAYHOSTS to RELAYURLS automatically.")
            
    if len(RELAYURLS) > 0 :
        log_syslog(f"relay urls: {RELAYURLS}")

    try:
        await asyncio.Future()  # run forever
    finally:
        for s in servers:
            s.close()
        await asyncio.gather(*(s.wait_closed() for s in servers))        

if __name__ == "__main__":
    asyncio.run(main())

