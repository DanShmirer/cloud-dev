#!/bin/bash

clear
echo "SSH to R-Pi..."

rpi_ip=$(head -1 $(dirname $0)/ips.txt | tail -2)
ssh -p 22 rpi@"$rpi_ip"
