#!/bin/bash
# Ping Google's DNS once with a 1-second timeout
if ping -c 1 -W 1 8.8.8.8 > /dev/null 2>&1; then
    echo -e "\[\033[1;36m\]● ONLINE" # Cyan
else
    echo -e "\[\033[1;31m\]○ OFFLINE" # Red
fi
