# petitban

1. **petitban** is a lightweight IP ban system for FreeBSD using **ipfw2 lookup tables.**  
2. It doesn't perform log parsing by itself and is intended to be driven by external log analyzers or event sources.
3. petitban is not a fail2ban replacement.

It consists of:

- `petitban_daemon.py` — background daemon that manages ipfw table entries  
- `petitban_send.py` — command-line sender that notifies the daemon  
- `petitban_wrapper.sh` — Apache piped‑log wrapper used to feed ban events

---

## Features

- FreeBSD‑native IP blocking using **ipfw2 lookup tables**
- The Python daemon receives add/del requests and manages the lookup table
- Lightweight sender script (`petitban_send.py`)
- Apache SSL VirtualHost compatible (uses piped log, not mod_ext_filter)
- Designed for log‑driven or event‑driven banning
- BAN-IP data can be shared across multiple petitban instances.
- rc.d integration included

---

## Installation (FreeBSD Ports)

1. This section describes installation via the FreeBSD Ports system.
2. Manual installation is possible but not documented here.

### 1. Extract the ports skeleton

If you downloaded petitban-ports-x.x.tar.gz into your home directory:

 * The ports skeleton is only required the first time.

```
k896951@host: ~# su
Password:
root@host:/home/k896951 #
root@host:/home/k896951 # mkdir -p /usr/ports/sysutils/petitban
root@host:/home/k896951 # cd /usr/ports/sysutils/petitban
root@host:/usr/ports/sysutils/petitban #  tar xzf ~/petitban-ports-x.x.tar.gz
```

### 2. Build and install

Then install:

```
root@host:/usr/ports/sysutils/petitban # make install clean
```

---

## Configuration

ipfw2 lookup table creation:

```
root@host:/root # ipfw table 80 create
```
It's best to simply create lookup table 80 using a custom ipfw2 script.

The following is a sample script.

⚠️ WARNING:

This example script flushes all existing ipfw rules.
Do not use it as-is on a production system unless you fully understand its effects.

If no lookup table is specified, table 80 is assumed.
petitban never creates or destroys ipfw tables by itself; it only modifies existing tables.

```/etc/ipfw.rules
#!/bin/sh

fwcmd="/sbin/ipfw"

${fwcmd} -q flush

${fwcmd} -q table 80 create type addr
${fwcmd} table 80 flush

${fwcmd} add 00100 allow ip from any to any via lo0
${fwcmd} add 00200 deny ip from any to 127.0.0.0/8
${fwcmd} add 00300 deny ip from 127.0.0.0/8 to any
${fwcmd} add 00400 deny ip from any to ::1
${fwcmd} add 00500 deny ip from ::1 to any
${fwcmd} add 00600 allow ipv6-icmp from :: to ff02::/16
${fwcmd} add 00700 allow ipv6-icmp from fe80::/10 to fe80::/10
${fwcmd} add 00800 allow ipv6-icmp from fe80::/10 to ff02::/16
${fwcmd} add 00900 allow ipv6-icmp from any to any icmp6types 1
${fwcmd} add 01000 allow ipv6-icmp from any to any icmp6types 2,135,136

${fwcmd} add 02000 deny ip from "table(80)" to any
${fwcmd} add 02001 allow tcp from any to me 443 in setup
${fwcmd} add 02002 deny tcp from any to me 443 in tcpflags fin,psh,urg
${fwcmd} add 02003 deny tcp from any to me 443 in tcpflags syn,fin
${fwcmd} add 02004 deny tcp from any to me 443 in tcpflags !syn,!ack,!rst

${fwcmd} add 65000 allow ip from any to any
${fwcmd} add 65535 count ip from any to any not // orphaned dynamic states counter
${fwcmd} add 65535 deny ip from any to any
```

Default config file:

`/usr/local/etc/petitban.conf` defines how petitban listens for local BAN-IP events, accepts SYNC requests from other instances, and optionally relays BAN-IP updates across multiple hosts.

All values are read at startup and normalized for safety (hostnames are resolved to IP addresses).

  Example:
  ```
  [DEFAULT]
  IPFWCMD=/sbin/ipfw
  DEFAULT_IPFW_TABLE=80
  EXCLUDEIPS=127.0.0.1
  
  # inner endpoint (local BAN-IP events)
  LISTEN_ADDR=127.0.0.1
  LISTEN_PORT=8765
  
  # outer endpoint (receiving SYNC from other instances)
  OUTER_LISTEN_ADDR=
  OUTER_LISTEN_PORT=8765
  OUTER_ALLOWED_HOST=
  
  # relay hosts (sending SYNC to remote instances)
  RELAYHOSTS=
  RELAYPORT=8765
  RELAYPATH=/
  ```

### **petitban.conf parameters**

- **LISTEN_ADDR / LISTEN_PORT**  
  Local WebSocket endpoint used by `petitban_send.py`.  
  Hostnames are resolved to IP addresses at startup.  
  Used for receiving local BAN-IP events.

- **OUTER_LISTEN_ADDR / OUTER_LISTEN_PORT**  
  Optional external WebSocket endpoint for receiving `SYNC` messages from remote petitban instances.  
  Leave `OUTER_LISTEN_ADDR` empty to disable external sync.

- **OUTER_ALLOWED_HOST**  
  Comma‑separated list of allowed remote hosts.  
  Hostnames are resolved to IP addresses at startup and compared against the `X-Forwarded-For` header.  
  Only these hosts are permitted to send BAN-IP sync requests.

- **RELAYHOSTS**  
  List of remote petitban instances to send BAN-IP updates to.  
  Hostnames are intentionally **not normalized** because relay connections may require `wss://` via a reverse proxy.  
  Used for BAN-IP sharing across multiple instances.

- **RELAYPORT / RELAYPATH**  
  Port and path used when connecting to remote relay hosts.

- **EXCLUDEIPS**  
  IP addresses that should never be added to the firewall table.  
  Useful for protecting internal services or monitoring hosts.

- **DEFAULT_IPFW_TABLE**  
  Default ipfw table number used when no table is specified.

### **BAN-IP sharing**

petitban supports sharing BAN-IP events across multiple instances.  
This works over WebSocket (`ws://`).  
When sharing BAN-IP information **over the Internet**, use a WebSocket reverse proxy (e.g., Apache `mod_proxy_wstunnel`) to provide secure `wss://` access.

When exposing this feature over the Internet, use a WebSocket reverse proxy such as Apache mod_proxy.  
Note: Apache 2.4.58+ integrates WebSocket support into mod_proxy, so mod_proxy_wstunnel is no longer available as a separate module.



/etc/rc.conf:

Add a line to the petitban settings.

  ```
  petitban_daemon_enable="YES"
  ```

---

## BAN-IP Sharing Examples

### 1. BAN-IP sharing on LAN
The following example shows how BAN-IP sharing works inside a LAN environment.
<img width="1115" height="566" alt="image" src="https://github.com/user-attachments/assets/6bfcf8a0-e470-426b-b05c-4a88be9b8661" />

---

### 2. BAN-IP sharing via Reverse Proxy (wss)
The following example shows how to share BAN-IP information over the Internet using a WebSocket reverse proxy.
<img width="1117" height="684" alt="image" src="https://github.com/user-attachments/assets/1b726d54-e8e6-4b0a-aefe-c5158a8ca7da" />

---

## Usage

All commands must be executed as root.

Start the daemon:
```
root@host:/root # service petitban_daemon start
```

Stop the daemon:
```
root@host:/root # service petitban_daemon stop
```

Ban an IP manually:
```
root@host:/root # petitban_send.py 80 ADD 192.0.2.10
```
or 
```
root@host:/root # petitban_send.py ADD 192.0.2.10
```
If no table number is specified in the arguments, the DEFAULT_IPFW_TABLE setting will be applied.

Check ipfw table:
```
root@host:/root # ipfw table 80 list
```
---

# Apache Integration (SSL‑compatible)

petitban integrates with Apache via **piped logs** (not mod_ext_filter).  
This works reliably under SSL VirtualHosts.

Apache will:

1. .htaccess checks whether the request is suspicious  
2. If suspicious, it sets USE_PETITBAN=1
3. CustomLog with env=USE_PETITBAN triggers the wrapper  
4. The wrapper receives the client IP and URL and calls petitban_send.py

---

## 1. `.htaccess` — define ban conditions

```apache
RewriteEngine On

RewriteCond %{REQUEST_URI} (/php|php/) [NC,OR]
RewriteCond %{REQUEST_URI} \.\. [NC,OR]
RewriteCond %{REQUEST_URI} \.(git|env|bak|exe) [NC,OR]
RewriteCond %{REQUEST_URI} /bin/[bckz]*sh [NC,OR]
RewriteCond %{REQUEST_URI} /(wp\-|cgi\-bin|owa|oracle|admin) [NC,OR]
RewriteCond %{REQUEST_URI} (owa|oracle|admin|server)/ [NC]
RewriteRule ^ - [E=USE_PETITBAN:1]
```
This sets USE_PETITBAN=1 only for suspicious requests.


## 2. httpd-ssl.conf — piped log (SSL‑safe)
```
  CustomLog "|/usr/local/bin/petitban_wrapper.sh" "%a %U%q" env=USE_PETITBAN
```
%a → client IP

%U%q → URL + query

wrapper is executed only when USE_PETITBAN=1


## 3. /usr/local/bin/petitban_wrapper.sh

```petitban_wrapper.sh
#!/bin/sh

bancmd="/usr/local/bin/petitban_send.py"

# Apache passes one line: "<IP> <URL>"
while read ip url; do
    ${bancmd} ADD "$ip" "AUTO,PATH=$url" &
done
```

Notes:
- wrapper is only invoked when USE_PETITBAN=1
- petitban_send.py is called with IP and metadata
- petitban_send.py does not read stdin → wrapper must pass arguments
- wrapper returns the log line unchanged

Example: SSH brute‑force detection (external feeder)

petitban_send.py requires arguments, so stdin cannot be piped directly.

Example watcher:

This is only an example; no deduplication or rate limiting is performed.
```
#!/bin/sh
tail -F /var/log/auth.log | \
  grep --line-buffered "Failed password" | \
  awk '{print $11}' | \
  while read ip; do
      /usr/local/bin/petitban_send.py ADD "$ip"
  done
```

## Design

petitban intentionally minimizes its scope.

It manages only the entries in the ipfw2 lookup table, delegating the discovery logic to an external solution.

This ensures auditability and ease of debugging.

## License

BSD 2‑Clause License

