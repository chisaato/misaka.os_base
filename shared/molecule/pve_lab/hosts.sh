#!/bin/sh
# 空载实验专用：同一 MAC 的 DHCP 租约地址，仅更新 guest，不配置宿主网络。
set -eu
address=$(ip -4 -o address show scope global | awk 'NR==1 {split($4,a,"/"); print a[1]}')
test -n "$address"
case "$address" in 127.*|0.*) exit 2 ;; esac
temporary=$(mktemp /etc/hosts.misaka.XXXXXX)
trap 'rm -f "$temporary"' EXIT
printf '127.0.0.1 localhost\n%s pve-lab.lab.invalid pve-lab\n::1 localhost ip6-localhost ip6-loopback\n' "$address" > "$temporary"
chmod 0644 "$temporary"
if cmp -s "$temporary" /etc/hosts; then exit 0; fi
cat "$temporary" > /etc/hosts
exit 10
