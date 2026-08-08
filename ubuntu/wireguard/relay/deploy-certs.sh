#!/bin/sh -e
# lego -> HAProxy: собирает pem (crt+key) и перечитывает haproxy, если серт изменился
SRC=/usr/local/etc/ssl/lego/certificates
DST=/etc/haproxy/certs
rc=1
for crt in "$SRC"/*.crt; do
  case "$crt" in *.issuer.crt) continue;; esac
  domain=$(basename "$crt" .crt)
  tmp="$DST/.$domain.pem.tmp"
  cat "$crt" "$SRC/$domain.key" > "$tmp"
  chmod 600 "$tmp"
  if ! cmp -s "$tmp" "$DST/$domain.pem" 2>/dev/null; then
    mv "$tmp" "$DST/$domain.pem"
    rc=0
  else
    rm -f "$tmp"
  fi
done
[ $rc -eq 0 ] && systemctl reload haproxy
exit 0
