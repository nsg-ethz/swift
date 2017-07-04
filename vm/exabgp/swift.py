#!/usr/bin/env python
# To be used with ExaBGP v3.4

import sys
import os
import subprocess
import json
import time
import select
import socket
import signal
from netaddr import *
from random import randint
from fcntl import fcntl, F_GETFL, F_SETFL
from os import O_NONBLOCK, read

swift_port = randint(3000,4000)

process = subprocess.Popen("python /root/SWIFT/swift/code/swift.py --port "+str(swift_port)+' --silent --run_encoding_threshold 1000', \
    shell=True, stdout=subprocess.PIPE, preexec_fn=os.setsid)
time.sleep(2)

def signal_handler(sig, frame):
    global process

    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    sys.exit(1)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Connect to SWIFT
sock_swift = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock_swift.connect(('localhost', swift_port))
except:
    signal_handler(signal.SIGTERM, None)

# set process.stdout in NONBLOCKING mode
flags = fcntl(process.stdout, F_GETFL)
fcntl(process.stdout, F_SETFL, flags | O_NONBLOCK)
# set sys.stdin in NONBLOCKING mode
flags = fcntl(sys.stdin, F_GETFL)
fcntl(sys.stdin, F_SETFL, flags | O_NONBLOCK)

sock_list = [sys.stdin, process.stdout]
data_stdin = ''
data_swift = ''

while True:
    inready, outready, excepready = select.select (sock_list, [], [])

    #try:
    for sock in inready:
        if sock == sys.stdin:
            data_tmp = sock.read(100000)
            next_data = ''
            data_stdin += data_tmp
            while len(data_stdin) > 0 and data_stdin[-1] != '\n':
                next_data = data_stdin[-1]+next_data
                data_stdin = data_stdin[:-1]

            for line in data_stdin.rstrip('\n').split('\n'):

                try:
                    bgp_message = json.loads(line)
                except ValueError:
                    pass

                peer_ip = bgp_message['neighbor']['ip']
                peer_asn = '-1'

                if 'message' in bgp_message['neighbor']:
                    if 'update' in bgp_message['neighbor']['message']:
                        bgp_update = bgp_message['neighbor']['message']['update']
                        if 'announce' in bgp_update:

                            aspath = bgp_update['attribute']['as-path']
                            peer_asn = str(aspath[0])

                            for nexthop in bgp_update['announce']['ipv4 unicast']:
                                for prefix in bgp_update['announce']['ipv4 unicast'][nexthop]:
                                    sock_swift.send('BGPSTREAM|exabgp|'+'A|'+str(peer_ip)+'|'+str(peer_asn)+'|'+str(int(time.time()))+'|'+str(prefix)+'|'+str(' '.join(map(lambda x:str(x), aspath)))+'\n')

                        elif 'withdraw' in bgp_update:
                            if 'ipv4 unicast' in bgp_update['withdraw']:
                                for prefix in bgp_update['withdraw']['ipv4 unicast']:
                                    sock_swift.send('BGPSTREAM|exabgp|'+'W|'+str(peer_ip)+'|'+str(peer_asn)+'|'+str(int(time.time()))+'|'+str(prefix)+'|'+'\n')

            data_stdin = next_data


        elif sock == process.stdout:

            data_tmp = sock.read(100000)
            next_data = ''
            data_swift += data_tmp
            while len(data_swift) > 0 and data_swift[-1] != '\n':
                next_data = data_swift[-1]+next_data
                data_swift = data_swift[:-1]

            for line in data_swift.rstrip('\n').split('\n'):
                if line.startswith('A|') or line.startswith('W|'):
                    linetab = line.split('|')
                    msgtype = linetab[0]
                    prefix = linetab[1]

                    # Advertisement
                    if msgtype == 'A':
                        nexthop = linetab[2]
                        aspath = linetab[4]
                        sys.stdout.write('neighbor 2.0.0.1 announce route '+prefix+' next-hop '+nexthop+' as-path [ '+aspath+ ' ]'+'\n')
                        sys.stdout.flush()

                    elif msgtype == 'W': # Withdrawal
                        sys.stdout.write ('withdraw route '+prefix+'\n')
                        sys.stdout.flush()

            data_swift = next_data

    #except:
    #    signal_handler(signal.SIGTERM, None)
