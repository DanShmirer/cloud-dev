#!/bin/bash

clear
echo "SSH to Worker-1..."

w1_ip=$(head -2 $(dirname $0)/ips.txt | tail -1)
ssh -p 22 worker1@"$w1_ip"
