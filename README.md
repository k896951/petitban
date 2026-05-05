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

### 2. Place the distfile

If you downloaded petitban-x.x.tar.gz into your home directory:

```
root@host:/home/k896951 # cp petitban-x.x.tar.gz /usr/ports/distfiles/
```

### 3. Build and install

Then install:

```
root@host:/home/k896951 # cd /usr/ports/sysutils/petitban
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

/usr/local/etc/petitban.conf

  Example:
  ```
  DEFAULT_IPFW_TABLE=80
  ```
If no lookup table is specified, table 80 is assumed.
petitban never creates or destroys ipfw tables by itself; it only modifies existing tables.

If no lookup table is specified, table 80 is assumed.
petitban never creates or destroys ipfw tables by itself; it only modifies existing tables.

/etc/rc.conf:

Add a line to the pritban settings.

  ```
  petitban_daemon_enable="YES"
  ```

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

