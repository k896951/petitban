# petitban

**petitban** is a lightweight IP ban system for FreeBSD using **ipfw2 lookup tables.**  
It consists of:

- `petitban_daemon.py` — background daemon that manages ipfw table entries  
- `petitban_send.py` — command-line sender that notifies the daemon  
- `petitban_wrapper.sh` — Apache piped‑log wrapper used to feed ban events

---

## Features

- FreeBSD‑native IP blocking using **ipfw2 lookup table**
- The Python daemon will receive add/del requests and manipulate the lookup table
- Lightweight sender script (`petitban_send.py`)
- Apache SSL VirtualHost compatible (uses piped log, not ExtFilter)
- Designed for log‑driven or event‑driven banning
- rc.d integration included

---

## Installation (FreeBSD Ports)

Place the ports skeleton under:

/usr/ports/sysutils/petitban/

Then install:
```
root@host:/root # cd /usr/ports/sysutils/petitban
root@host:/usr/ports/sysutils/petitban # make install clean
```

---

## Configuration

ipfw2 lookup table createtion:
```
root@host:/root # ipfw table 80 create
```

Default config file:

/usr/local/etc/petitban.conf

  Example:
  ```
  DEFAULT_IPFW_TABLE=80
  ```
If no lookup table is specified, table 80 is assumed.

---

## Usage

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

petitban integrates with Apache via **piped logs**, not ExtFilter.  
This works reliably under SSL VirtualHosts.

Apache will:

1. `.htaccess` checks whether the request is suspicious  
2. If suspicious → sets `USE_PETITBAN=1`  
3. `CustomLog` with `env=USE_PETITBAN` triggers the wrapper  
4. wrapper receives the client IP and URL, and calls petitban_send.py

---

## 1. `.htaccess` — define ban conditions

```apache
RewriteEngine On

RewriteCond %{REQUEST_URI} (/php|php/) [NC,OR]
RewriteCond %{REQUEST_URI} \.\. [NC,OR]
RewriteCond %{REQUEST_URI} \.(git|env|bak|exe) [NC,OR]
RewriteCond %{REQUEST_URI} /bin/[bckz]*sh [NC,OR]
RewriteCond %{REQUEST_URI} (wp\-|cgi\-bin|owa|oracle|admin|server)/ [NC]
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
```
#!/bin/sh
tail -F /var/log/auth.log | \
  grep --line-buffered "Failed password" | \
  awk '{print $11}' | \
  while read ip; do
      /usr/local/bin/petitban_send.py ADD "$ip"
  done
```

## License

BSD 2‑Clause License

