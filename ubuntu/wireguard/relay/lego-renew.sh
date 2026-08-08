#!/bin/sh -e
# Еженедельное продление (systemd timer lego-renew.timer)
export LEGO_CONFIG=/usr/local/etc/lego/lego.yml
output=$(/usr/bin/lego renew --days 30 2>&1) || (echo "$output" && exit 1)
[ -n "$output" ] && echo "$output"
/usr/local/sbin/deploy-certs.sh
