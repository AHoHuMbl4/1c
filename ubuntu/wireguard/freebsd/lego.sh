#!/bin/sh -e
# Еженедельное продление (periodic 604.lego, юзер _lego)
export LEGO_CONFIG=/usr/local/etc/lego/lego.yml
output=$(/usr/local/bin/lego renew --days 30 2>&1) || (echo "$output" && exit 1)
[ -n "$output" ] && echo "$output"
