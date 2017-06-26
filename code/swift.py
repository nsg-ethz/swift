import sys
import os
import socket
import select
import argparse
import time
import pickle
import signal
import logging
import logging.handlers
import multiprocessing
import errno

from peer import run_peer, peer_init_logger
from peer_bpavalidation import run_peer_bpavalidation, peer_bpavalidation_init_logger
from subprocess import Popen, PIPE
from bgp_messages import parse
from rib import rib_global, rib_init_logger

try:
    os.chdir(os.path.dirname(__file__))
except:
    pass

parser = argparse.ArgumentParser("This is the server listening for bgp messages.")
parser.add_argument("--port", type=int, default=3000, help="Server port")
parser.add_argument("--win_size", default=10, type=int, help="Size of the window (seconds)")
parser.add_argument("--start_stop", default='1500,9', type=str, help="Minimum number of withdrawals \
to receive within the a period of time to start and end the burst. start and end sperated by a comma.")
parser.add_argument("--min_burst_size", default=2500, type=int, help="Minimum burst size required to execute bpa.")
parser.add_argument("--bpa_freq", default=2500, type=int, help="BPA frequency execution (in number of withdrawals).")
parser.add_argument("--p_w", default=1, type=float, help="Weight on the precision when computing the FM score. (if 0 and 0 for both weights, the naive approach is used instead of BPA.)")
parser.add_argument("--r_w", default=3, type=float, help="Weight on the recall when computing the FM score.")
parser.add_argument("--bpa_algo", default='bpa-multiple', type=str, help="Algoeithm used. 3 options: naive, bgp-single, bpa-multiple.")
parser.add_argument("--nb_bits_aspath", default=28, type=int, help="Number of bits reserver for the AS path compression.")
parser.add_argument("--nb_bits_nexthop", default=3, type=int, help="Number of bits reserved for the each nexthop (primary or backup).")
parser.add_argument("--run_encoding_threshold", default=1000000, type=int, help="Compute the encoding after a certain amount of routes received. Otherwise the encoding is computed when the first withdrawal is received.")
parser.add_argument("--no_rib", action='store_false', default=True, help="When this option is set, the RIB is not maintain. Useful when you only need to test BPA or the encoding.")
parser.add_argument("--bpa_validation", action='store_true', default=False, help="Print bursts information. Set to True if you do want to print this and make SWIFT as fast as possible.")
parser.add_argument("--silent", action='store_true', default=False, help="Print bursts information. Set to True if you do want to print this and make SWIFT as fast as possible.")
parser.add_argument("--bursts_dir", default='bursts', help="Directory where to store information about the bursts prediction (default bursts)")
parser.add_argument("--log_dir", default='log', help="Directory where to store the logs (default log)")

args = parser.parse_args()
port = args.port
win_size = args.win_size
withdr_start_end = args.start_stop
min_bpa_burst_size = args.min_burst_size
fm_freq = args.bpa_freq
p_w = args.p_w
r_w = args.r_w
bpa_algo = args.bpa_algo
nb_bits_aspath = args.nb_bits_aspath
nb_bits_nexthop = args.nb_bits_nexthop
global_rib_enabled = args.no_rib
bpa_validation = args.bpa_validation
silent = args.silent
run_encoding_threshold = args.run_encoding_threshold
bursts_dir = args.bursts_dir
log_dir = args.log_dir

# Initialize the logger for the peer and rib processes
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
if not bpa_validation:
    peer_init_logger(log_dir)
else:
    peer_bpavalidation_init_logger(log_dir)
rib_init_logger(log_dir)

# Create the bursts dir if it does not exist
if not os.path.exists(bursts_dir):
    os.makedirs(bursts_dir)

# Define the logger
main_logger = logging.getLogger('MainLogger')
main_logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s')
handler = logging.handlers.RotatingFileHandler(log_dir+'/main', maxBytes=200000000000, backupCount=5)
handler.setFormatter(formatter)
main_logger.addHandler(handler)

if not 'bpa-multiple' == bpa_algo and not 'bpa-single' == bpa_algo and not 'naive' == bpa_algo:
    main_logger.error('Unknown algorithm')
    print 'Error: unknown algo.'
    sys.exit(0)

function_peer = run_peer
if bpa_validation:
    function_peer = run_peer_bpavalidation

# Dictionnary of peers - child processes
peer_dic = {}
# Dictionnary of queues
queue_dic = {}

# Define the number of withdrawals required to start and end a burst
nb_withdrawals_burst_start = int(withdr_start_end.split(',')[0])
nb_withdrawals_burst_end = int(withdr_start_end.split(',')[1])

# Starts the global RIB process. All the peer processes will communicate with this process
socket_rib_name = 'socket_tmp_'+str(port)
global_rib_process = multiprocessing.Process(target=rib_global, args=(port+1,nb_bits_nexthop, 'backup_avaibility', socket_rib_name,))
global_rib_process.start()
main_logger.info('Started the global RIB.')


if not os.path.exists('bursts'):
    os.makedirs('bursts')

with open('bursts/bursts_info', 'w') as fd:
    fd.write('#\tw_threshold:\t'+str(nb_withdrawals_burst_start)+','+str(nb_withdrawals_burst_end)+'\t'+str(win_size)+'\t'+str(min_bpa_burst_size)+'\t'+str(fm_freq)+'\t'+str(p_w)+'\t'+str(r_w)+'\n')

# Exit properly when receiving SIGINT, refresh the peer dic upon reception of a SIGCHLD
def signal_handler(sig, frame):
    global peer_dic
    global global_rib_process

    if sig == signal.SIGINT or sig == signal.SIGTERM:
        main_logger.info('Received SIGINT. Exiting.')
        socket.close()

        for k, v in peer_dic.items():
            try:
                v.terminate()
            except:
                pass

        global_rib_process.terminate()

        os._exit(1)

    elif sig == signal.SIGCHLD:
        for peer_id in peer_dic.keys():
            try:
                if not peer_dic[peer_id].is_alive():
                    del peer_dic[peer_id]
                    del queue_dic[peer_id]
                    main_logger.info('Clean child '+str(peer_id))
            except KeyError:
                pass

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGCHLD, signal_handler)

socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
socket.bind(('', port))
socket.listen(5)
print 'Waiting for new connection...'

sock_list = [socket]
data = ''

while True:
    try:
        inready, outready, excepready = select.select (sock_list, [], [])
    except select.error, v:
        if v[0] != errno.EINTR:
            raise
        else:
            continue

    try:
        for sock in inready:
            if sock == socket:
                (newsock, address) = sock.accept()
                sock_list.append(newsock)
                print 'New connection from ', address
            else:
                data_tmp = sock.recv(100000000)

                if len(data_tmp) == 0:
                    main_logger.info('Disconnected from '+str(sock.getpeername()))
                    print 'Disconnected from '+str(sock.getpeername())
                    sock.close()
                    sock_list.remove(sock)
                else:
                    data += data_tmp

                    next_data = ''
                    while data[-1] != '\n':
                        next_data = data[-1]+next_data
                        data = data[:-1]

                    for line in data.rstrip('\n').split('\n'):
                        tmp = time.time()
                        try:
                            bgp_msg = parse(line)
                        except:
                            if 'EXIT' in line: # Stop SWIFT
                                os.kill(os.getpid(), signal.SIGINT)
                            else:
                                print 'Error: '+line
                                bgp_msg = None

                        if bgp_msg is not None:
                            if bgp_msg.peer_id not in peer_dic:
                                if len(peer_dic) <= 500:
                                    main_logger.info('Starting new peer '+bgp_msg.peer_id)
                                    queue_dic[bgp_msg.peer_id] = multiprocessing.Queue()
                                    peer_dic[bgp_msg.peer_id] = multiprocessing.Process(target=function_peer, \
                                    args=(queue_dic[bgp_msg.peer_id], win_size, nb_withdrawals_burst_start, \
                                    nb_withdrawals_burst_end, min_bpa_burst_size, bursts_dir, \
                                    socket_rib_name, fm_freq, p_w, \
                                    r_w, bpa_algo, nb_bits_aspath, run_encoding_threshold, \
                                    global_rib_enabled, silent))
                                    peer_dic[bgp_msg.peer_id].start()
                                else:
                                    print 'Cannot accept new peers, limit (500) reached.'
                                    main_logger.warning('Cannot accept new peers, limit (500) reached.')
                            if bgp_msg.peer_id in peer_dic:
                                try:
                                    queue_dic[bgp_msg.peer_id].put(bgp_msg)
                                except IOError:
                                    main_logger.info('Peer '+bgp_msg.peer_id+' disconnected')
                                    peer_dic[bgp_msg.peer_id].terminate()
                                    break
                    data = next_data
    # Clean exit
    except select.error, KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
