import sys
import os
import time
import argparse
import select
import cPickle as pickle
import signal
import atexit
from copy import deepcopy
import logging.handlers
import multiprocessing
import string

from bgp_messages import parse, BGPMessagesQueue
from rib import RIBPeer
from burst import Burst

## Parameters used for the loggers
peer_logger = None
log_dir = None
formatter = None
handler = None

# Initialize the main peer logger
def peer_bpavalidation_init_logger(logdir_name):
    global peer_logger
    global log_dir
    global formatter
    global handler

    peer_logger_loc = logging.getLogger('PeerLogger')
    peer_logger_loc.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s')
    handler = logging.handlers.RotatingFileHandler(logdir_name+'/peers', maxBytes=200000000000000, backupCount=5)
    handler.setFormatter(formatter)
    peer_logger_loc.addHandler(handler)

    peer_logger_loc.info('Peer launched!')
    peer_logger = peer_logger_loc
    log_dir = logdir_name


"""
The main function executed when launching a new peer.
queue           is the shared queue between the main process and the peer processes
win_size        is the window_size
nb_withdrawals_burst_start     the number of withdrawals we need to receive in last 5ec to start the burst
nb_withdrawals_burst_end        the number of withdrawals we need to receive in last 5ec to end the burst
min_bpa_burst_size  Minimum burst size before starting to run BPA
burst_outdir    where to store information about the bursts (silent needs to False)
nb_withdraws_per_cycle After how many new withdrawals BPA needs to run_peer
silent          print output in files to get information. To speed-up the algo, set to True.
naive           Use the naive approach if True
"""
def run_peer_bpavalidation(queue, win_size, nb_withdrawals_burst_start, \
nb_withdrawals_burst_end, min_bpa_burst_size, burst_outdir, \
nb_withdraws_per_cycle=100, p_w=1, r_w=1, bpa_algo=False, nb_bits_aspath=33, \
run_encoding_threshold=1000000, global_rib_enabled=True, silent=False):

    import socket

    try:
        os.nice(-20)
    except OSError:
        peer_logger.info('Cannot change the nice.')

    # Last time the peer wrote the rib and queue size in the log file
    last_log_write = 0

    # Socket connected to the global RIB
    socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

    # Current burst (if any)
    current_burst = None

    # Exit properly when receiving SIGINT
    def signal_handler(signal, frame):
        if current_burst is not None:
            current_burst.stop(bgp_msg.time)

        socket.close()
        peer_logger.info('Received SIGTERM. Exiting.')
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)

    peer_id = None
    peer_as = None

    # Create the RIB for this peer
    rib = RIBPeer()

    U_queue = BGPMessagesQueue(win_size) # Queue of Updates (advertisement or withdrawals)

    last_ts = 0

    while True:

        while True:
            bgp_msg = queue.get()

            if bgp_msg is not None:
                if peer_id is None:
                    peer_id = bgp_msg.peer_id
                    peer_as = bgp_msg.peer_as
                    peer_as_set = set()
                    last_ts = bgp_msg.time
                    last_log_write = bgp_msg.time
                    peer_ip = peer_id.split('-')[-1]

                    peer_handler = logging.handlers.RotatingFileHandler(log_dir+'/peer_'+str(peer_id), maxBytes=200000000000000, backupCount=5)
                    peer_handler.setFormatter(formatter)
                    peer_logger.removeHandler(handler)
                    peer_logger.addHandler(peer_handler)

                    peer_logger.info('Peer_'+str(peer_id)+'_(AS'+str(str(peer_as))+')_started.')

                    if bgp_msg.as_path is not None and len(bgp_msg.as_path) > 0:
                        if peer_as != bgp_msg.as_path[0]:
                            peer_logger.warning('Peer AS '+str(peer_as)+' and first AS '+str(bgp_msg.as_path[0])+' in AS path does not match. Setting first AS as peer AS.')
                            peer_as = bgp_msg.as_path[0]

                if peer_id != bgp_msg.peer_id:
                    peer_logger.critical('Received a bgp_message with peer_id: '+str(bgp_msg.peer_id))

                if bgp_msg.mtype == 'A':
                    # Update the RIB for this peer
                    bgp_msg.as_path = rib.update(bgp_msg)

                    # Update the queue of updates
                    if bgp_msg.as_path != []:
                        U_queue.append(bgp_msg)

                elif bgp_msg.mtype == 'W':
                    # Update the RIB for this peer
                    bgp_msg.as_path = rib.withdraw(bgp_msg)

                    # Update the queue of withdraws
                    if bgp_msg.as_path != []:
                        U_queue.append(bgp_msg)

                else:
                    peer_logger.info(bgp_msg)

                # Print size of hte queue for each second
                while last_log_write < bgp_msg.time:
                    # Refresh the queue
                    U_queue.refresh(last_log_write)
                    peer_logger.info(str(int(last_log_write))+' '+str(len(rib))+' '+str(len(U_queue)))
                    last_log_write += 1

                # Stop the burst if the size of the queue is lower than the threshold
                if current_burst is not None:
                    if len(U_queue) < nb_withdrawals_burst_end:
                        current_burst.stop(bgp_msg.time)
                        current_burst = None
                    else:
                        current_burst.add_real_prefix(bgp_msg.time, bgp_msg.prefix, bgp_msg.mtype, bgp_msg.as_path)

                # Create a burst if the size of the is higher than the threshold
                if current_burst is None:
                    if len(U_queue) > nb_withdrawals_burst_start:
                        burst_start_time = U_queue[100].time if len(U_queue) > 100 else U_queue[0].time
                        current_burst = Burst(peer_id, bgp_msg.time, win_size, burst_outdir, burst_start_time, silent)
