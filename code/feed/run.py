import time
import datetime
import socket
import argparse
from datetime import date

from _pybgpstream import BGPStream, BGPRecord, BGPElem

parser = argparse.ArgumentParser("This script connects to a server and sends bgp messages read from bgpstream.")
parser.add_argument("--dst_ip", type=str, help="Server IP")
parser.add_argument("--port", type=int, help="Port")
parser.add_argument("--collectors", type=str, help="List of collectors separated by a comma.")
parser.add_argument("--start_time", type=int, help="Start time (timestamp).")
parser.add_argument("--stop_time", type=int, help="Stop time (timestamp).")
parser.add_argument("--peers_ip", default='no', type=str, help="List IP separated by comma \
(Default all the peers belonging to the collectors).")
parser.add_argument("--peers_file", default='no', type=str, help="List of peer IP in file, one per line .")

args = parser.parse_args()
dst = args.dst_ip
port = args.port
collectors = args.collectors
start_time_ts = args.start_time
stop_time_ts = args.stop_time
peers_ip = args.peers_ip
peers_file = args.peers_file

filter_peer = set()
if peers_ip != 'no':
    for ip in peers_ip.rstrip('\n').split(','):
        filter_peer.add(ip)
if peers_file != 'no':
    with open(peers_file, 'r') as fd:
        for line in fd.readlines():
            filter_peer.add(line.rstrip('\n'))
print filter_peer

collectors = collectors.rstrip('\n').split(',')


peer_set = {}

def filter_play_updates(collectors, start_time_ts, stop_time_ts):
    stream = BGPStream()

    is_ripe = False

    for c in collectors:
        if 'rrc' in c:
            is_ripe = True
        stream.add_filter('collector', c)

    stream.set_data_interface_option('broker', 'url', 'https://bgpstream-dev.caida.org/broker')


    stream.add_filter('prefix', '0.0.0.0/0') # Only focus on IPV4
    stream.add_filter('record-type','ribs')
    stream.add_filter('record-type','updates')

    # Find the time when the last rib was available (every 2 hurs with routeviews)
    # 28800 if RIPE RIS, 7200 if RouteViews
    offset = 7200
    if is_ripe:
        offset = 28880

    rib_timestamp = start_time_ts
    while rib_timestamp%offset != 0:
        rib_timestamp -= 1
    rib_timestamp -= 600

    stream.add_interval_filter(rib_timestamp, stop_time_ts)
    stream.add_rib_period_filter(100000000000000000)

    return stream


def stream_ribfirst(stream, filter_peer):
    rec = BGPRecord()

    rib_started = False

    while(stream.get_next_record(rec)):
        if rec.status != "valid":
            print rec.project, rec.collector, rec.type, rec.time, rec.status
        else:
            if rec.type == 'rib':
                rib_started = True

            if rib_started:
                elem = rec.get_next_elem()
                while(elem):
                    if elem.peer_address in filter_peer or len(filter_peer) == 0:
                        if elem.type == 'W':
                            bgp_message = 'BGPSTREAM|'+str(rec.collector) \
                            +'|'+str(elem.type)+'|'+str(elem.peer_address) \
                            +'|'+str(elem.peer_asn)+'|'+str(elem.time)+'|'+str(elem.fields['prefix'])
                        elif 'as-path' in elem.fields:
                            as_path = elem.fields['as-path'].split('{')[0].split(',')[0].rstrip(' ')
                            bgp_message = 'BGPSTREAM|'+str(rec.collector) \
                            +'|'+str(elem.type)+'|'+str(elem.peer_address) \
                            +'|'+str(elem.peer_asn)+'|'+str(elem.time)+'|'+str(elem.fields['prefix']) \
                            +'|'+as_path
                        else:
                            bgp_message = None

                        #print 'YES'+'\t'+str(rec.project)+'\t'+str(rec.collector)+'\t'+str(rec.time)+'\t'+str(rec.type)+'\t'+str(rec.status)

                        if rec.collector not in peer_set:
                            peer_set[rec.collector] = set()
                        peer_set[rec.collector].add(elem.peer_address)

                        if bgp_message is not None:
                            yield bgp_message

                    elem = rec.get_next_elem()

            #else:
                #print 'NO'+'\t'+str(rec.project)+'\t'+str(rec.collector)+'\t'+str(rec.time)+'\t'+str(rec.type)+'\t'+str(rec.status)

stream = BGPStream()
stream = filter_play_updates(collectors, start_time_ts, stop_time_ts)
stream.start()

socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
socket.connect((dst, port))
print 'Connected to ',dst,' port ',port

for bgp_message in stream_ribfirst(stream, filter_peer):
    socket.send(bgp_message+'\n')

# Stop each peer
for c, peer_c in peer_set.iteritems():
    for p in peer_c:
        socket.send('BGPSTREAM|'+str(c)+'|CLOSE|'+str(p)+'|37989|'+'-1'+'|||||||||\n')

socket.close()
