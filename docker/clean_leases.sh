#!/bin/bash
#runs mosquitto_sub with a 2 seconds timeout
msg="$(timeout 2 mosquitto_sub -u "neon" -P "Canela8872" -t "dhcp/lease/#")"
#remove spaces from topics list
cmsg="$(echo -e "${msg}" | tr -d '[:space:]')"
#makes an array with each topic 
IFS="," read -ra macs <<< "$cmsg"
for mac in "${macs[@]}"
do
    if [[ $mac == *"mac"* ]]; then
        m="$(echo $mac | cut -d':' -f2)"
        m="$(echo $m | tr -d '"')"
        topic="dhcp/lease/${m}"
        #removes old retained message        
        mosquitto_pub -t "$topic" -u neon -P Canela8872 -r -n
    fi
done
