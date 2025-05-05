#!/usr/bin/python3

#
#  Copyright (C) 2025 Rafael Senties Martinelli. All Rights Reserved.
#

import sys

def anonymize_ipv4(ip:str) -> str:
    parts = ip.split('.')
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return f"{parts[0]}.{parts[1]}.0.0"

    raise ValueError(f"Invalid IPv4 address: {ip}")

def anonymize_ipv6(ip:str) -> str:
    parts = ip.split(':')
    if len(parts) > 1:
        return ':'.join(parts[:2]) + '::'

    raise ValueError(f"Invalid IPv6 address: {ip}")

def anonymize_ip(ip:str) -> str:
    if '.' in ip:
        return anonymize_ipv4(ip)

    elif ':' in ip:
        return anonymize_ipv6(ip)

    return ip

def anonymize_log_file(input_path:str, output_path:str):
    with open(input_path, 'r') as input_file, open(output_path, 'w') as output_file:
        for line in input_file:
            fields = line.split(' ')
            if fields:
                fields[0] = anonymize_ip(fields[0])
                output_file.write(' '.join(fields))
            else:
                output_file.write(line)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python anonymize_nginx_log_simple.py input.log output.log")
        sys.exit(1)

    anonymize_log_file(sys.argv[1], sys.argv[2])