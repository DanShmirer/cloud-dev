#!/bin/bash

clear
echo "SSH to Worker-2..."

w2_ip=$(head -1 $(dirname $0)/ips.txt | tail -2)
ssh -p 21 worker2@"$w2_ip"
