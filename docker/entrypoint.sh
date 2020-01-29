#!/bin/sh
if [ -e /usr/local/var/kea/kea-dhcp4.kea-dhcp4.pid ]; then
  rm /usr/local/var/kea/kea-dhcp4.kea-dhcp4.pid
fi
/clean_leases.sh
/usr/local/sbin/kea-dhcp4 -c /usr/local/etc/kea/kea-dhcp4.conf