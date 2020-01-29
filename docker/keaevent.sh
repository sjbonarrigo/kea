#!/bin/bash
mac="$(echo ${KEA_LEASE4_HWADDR} | tr -d ':')"
topic="dhcp/lease/${mac}"
event_timestamp=$(date "+%m-%d-%Y,%H:%M:%S")
case "$1" in
  "lease4_select" | "lease4_renew" )
  msg="{\"timestamp\":\"${event_timestamp}\",\"mac\":\"${mac}\",\"ip\":\"${KEA_LEASE4_ADDRESS}\"}"
  mosquitto_pub -t "$topic" -u neon -P Canela8872 -r -m "$msg"
  ;;
  "lease4_release"|"lease4_expire")
     mosquitto_pub -t "$topic" -u neon -P Canela8872 -r -n
  ;;
esac