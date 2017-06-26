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
from as_topology import ASTopology
from bpa import find_best_fmscore_forward, find_best_fmscore_backward, find_best_fmscore_naive, find_best_fmscore_single
from burst import Burst
from encoding import Encoding


# Parameters used for the loggers
peer_logger = None
log_dir = None
formatter = None
handler = None

# Initialize the main peer logger
def peer_init_logger(logdir_name):
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
This function runs the prefixes prediction. To do the prediction, BPA (single or mulitple)
can be used, with different weights on the precision and recall, or the naive
approach can be used. The failed links found, and their prefixes, are then
recorded in the burst object, and written in a file if silent is not enabled.
current_burst   The current burst
G               The graph of AS paths still available, weighted based on the number of prefixes traversing them
G_W             The graph of AS paths that have been withdrawn, weighted based on the number of withdrawn paths
W_queue         The queue of withdrawals.
p_w, r_w        The precision and recall weights
bpa_algo        The type of algoruthm to use (bpa-single, bpa-multiple, naive)
"""

def burst_prediction(current_burst, G, G_W, W_queue, p_w, r_w, bpa_algo, peer_as_set):
    current_burst.prediction_done = True

    try:
        if bpa_algo == 'bpa-multiple':
            best_edge_set_forward, best_fm_score_forward, best_TP_forward, best_FP_forward, best_FN_forward = \
            find_best_fmscore_forward(G, G_W, len(W_queue)+len(current_burst.deleted_from_W_queue), p_w, r_w, opti=True)
            best_edge_set_backward, best_fm_score_backward, best_TP_backward, best_FP_backward, best_FN_backward = \
            find_best_fmscore_backward(G, G_W, len(W_queue)+len(current_burst.deleted_from_W_queue), p_w, r_w, opti=True)

            if best_fm_score_forward > best_fm_score_backward:
                best_edge_set = best_edge_set_forward
                best_TP = best_TP_forward
                best_FP = best_FP_forward
                best_FN = best_FN_forward
                best_fm_score = best_fm_score_forward
            elif best_fm_score_backward > best_fm_score_forward:
                best_edge_set = best_edge_set_backward
                best_TP = best_TP_backward
                best_FP = best_FP_backward
                best_FN = best_FN_backward
                best_fm_score = best_fm_score_backward
            else: # backward and forward mode returns the same fm score
                best_edge_set = best_edge_set_forward.union(best_edge_set_backward)
                best_TP = -1
                best_FP = -1
                best_FN = -1
                best_fm_score = best_fm_score_forward

        elif bpa_algo == 'bpa-single':
            best_edge_set, best_fm_score, best_TP, best_FP, best_FN = find_best_fmscore_single(G, G_W, len(W_queue)+len(current_burst.deleted_from_W_queue), p_w, r_w)
        else:
            best_edge_set = set()
            best_TP = 0
            best_FP = 0
            best_FN = 0
            for peer_as in peer_as_set:
                best_edge_set_tmp, best_fm_score, best_TP_tmp, best_FP_tmp, best_FN_tmp = find_best_fmscore_naive(G, G_W, len(W_queue)+len(current_burst.deleted_from_W_queue), peer_as, p_w, r_w)
                best_edge_set = best_edge_set.union(best_edge_set_tmp)
                best_TP += best_TP_tmp
                best_FP += best_FP_tmp
                best_FN += best_FN_tmp

    except:
        peer_logger.critical('BPA has failed.')

    return best_edge_set, best_fm_score, int(best_TP), int(best_FP), int(best_FN)


def burst_add_edge(current_burst, rib, encoding, last_msg_time, best_edge_set, G, G_W, W_queue, silent):
    for new_edge in current_burst.add_edges_iter(last_msg_time, best_edge_set, G_W):
        for p in G.get_prefixes_edge(new_edge):
            aspath = rib.rib[p]
            is_encoded, depth = encoding.prefix_is_encoded(p, aspath, new_edge[0], new_edge[1])
            current_burst.add_predicted_prefix(last_msg_time, p, is_encoded, depth)

        for p in current_burst.deleted_from_W_queue:
            for i in range(0, len(p.as_path)-1):
                if (p.as_path[i] == new_edge[0] and p.as_path[i+1] == new_edge[1]) or (p.as_path[i+1] == new_edge[0] and p.as_path[i] == new_edge[1]):
                    current_burst.add_predicted_prefix2(p.time, p.prefix, True, 'D')
                    break

        for p in W_queue:
            for i in range(0, len(p.as_path)-1):
                if (p.as_path[i] == new_edge[0] and p.as_path[i+1] == new_edge[1]) or (p.as_path[i+1] == new_edge[0] and p.as_path[i] == new_edge[1]):
                    current_burst.add_predicted_prefix2(p.time, p.prefix, True, 'Q')
                    break

def send_fake_update(p, peer_ip, ts, rib, encoding, socket):
    # if it is an advertisement
    if rib is not None:
        # Make the second part of the v_mac (the part where the as-path is encoded)
        v_mac = ''
        deep = 1
        aspath = ''
        for asn in rib.rib[p]:
            if deep in encoding.mapping:
                depth_value = encoding.mapping[deep].get_mapping_string(asn)
                v_mac += ''+depth_value
            deep += 1
            aspath += str(asn)+' '
        aspath = aspath[:-1]

        v_mac = string.ljust(v_mac, encoding.max_bytes, '0')

        socket.send(peer_ip+'|'+p+'|'+str(ts)+'|'+aspath+'|'+v_mac+'\n')
    else: # If it is a withdrawal
        socket.send(peer_ip+'|'+p+'|'+str(ts)+'\n')


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
def run_peer(queue, win_size, nb_withdrawals_burst_start, \
nb_withdrawals_burst_end, min_bpa_burst_size, burst_outdir, socket_rib_name, \
nb_withdraws_per_cycle=100, p_w=1, r_w=1, bpa_algo=False, nb_bits_aspath=33, \
run_encoding_threshold=1000000, global_rib_enabled=True, silent=False):

    global peer_logger

    import socket

    try:
        os.nice(-20)
    except OSError:
        peer_logger.info('Cannot change the nice.')

    # Create the topologies for this peer
    G = ASTopology(1, silent) # Main topology
    G_W = ASTopology(nb_withdrawals_burst_start, silent) # Subset of the topology with the withdraws in the queue

    # Current burst (if any)
    current_burst = None

    # Last time the peer wrote the rib and queue size in the log file
    last_log_write = 0

    # Socket connected to the global RIB
    socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

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

    encoding = None
    # This function create and initialize the encoding
    def init_encoding():
        encoding = Encoding(peer_id, G, 'encoding', nb_bits_aspath, 5, output=True)
        encoding.compute_encoding()
        peer_logger.info(str(int(bgp_msg.time))+'\t'+str(len(rib))+'\t'+str(len(W_queue))+'\t'+'Encoding computed!')

        if global_rib_enabled:
            for p in rib.rib:
                send_fake_update(p, peer_ip, bgp_msg.time, rib, encoding, socket)

        return encoding

    #A_queue = BGPMessagesQueue(win_size) # Queue of Updates
    W_queue = BGPMessagesQueue(win_size) # Queue of Withdraws

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

                    # Make the connection with the global RIB
                    rib_global_socket_address = '/tmp/'+socket_rib_name
                    socket.connect(rib_global_socket_address)
                    peer_logger.info('Peer_'+str(peer_id)+'_(AS'+str(str(peer_as))+') connected with the global RIB.')

                if peer_id != bgp_msg.peer_id:
                    peer_logger.critical('Received a bgp_message with peer_id: '+str(bgp_msg.peer_id))

                if bgp_msg.mtype == 'A':
                    # Update the set set of peer_as (useful when doing the naive solution)
                    if len(bgp_msg.as_path) > 0:
                        peer_as_set.add(bgp_msg.as_path[0])

                    # Update the RIB for this peer
                    old_as_path = rib.update(bgp_msg)

                    # Remove the old as-path in the main graph for this prefix
                    G.remove(old_as_path, bgp_msg.prefix)

                    # Add the new as-path in both the main graph and the graph of advertisments
                    G.add(bgp_msg.as_path, bgp_msg.prefix)

                    # Update the encoding, and send the fake advertisement to the global RIB
                    if encoding is not None:
                        encoding.advertisement(old_as_path, bgp_msg.as_path)
                        if global_rib_enabled: send_fake_update(bgp_msg.prefix, peer_ip, bgp_msg.time, rib, encoding, socket)
                    elif len(rib.rib) > run_encoding_threshold:
                            encoding = init_encoding()

                elif bgp_msg.mtype == 'W':
                    # Create the encoding if not done yet
                    if encoding is None:
                        encoding = init_encoding()

                    # Update the RIB for this peer
                    bgp_msg.as_path = rib.withdraw(bgp_msg)

                    # Remove the old as-path in the main graph for this prefix
                    G.remove(bgp_msg.as_path, bgp_msg.prefix)

                    # Add the withdrawn as-path in the graph of withdraws
                    G_W.add(bgp_msg.as_path)

                    # Update the queue of withdraws
                    if bgp_msg.as_path != []:
                        W_queue.append(bgp_msg)

                    # Update the encoding
                    encoding.withdraw(bgp_msg.as_path)

                    # Send the withdrawal to the global RIB
                    if global_rib_enabled: send_fake_update(bgp_msg.prefix, peer_ip, bgp_msg.time, None, None, socket)


                elif bgp_msg.mtype == 'CLOSE':

                    # CLOSE this peer. Clear all the topologies, ribs, queues, bursts, etc
                    if current_burst is not None:
                        best_edge_set, best_fm_score, best_TP, best_FP, best_FN = burst_prediction(current_burst, G, G_W, W_queue, p_w, r_w, bpa_algo, peer_as_set)
                        current_burst.fd_predicted.write('PREDICTION_END_CLOSE|'+bpa_algo+'|'+str(len(current_burst))+'|'+str(best_fm_score)+'|'+str(best_TP)+'|'+str(best_FN)+'|'+str(best_FP)+'\n')
                        current_burst.fd_predicted.write('PREDICTION_END_EDGE|')
                        res = ''
                        depth = 9999999999
                        for e in best_edge_set:
                            depth = min(G_W.get_depth(e[0], e[1]), depth)
                            res += str(e[0])+'-'+str(e[1])+','

                        current_burst.fd_predicted.write(res[:len(res)-1]+'|'+str(depth)+'\n')

                        #G_W.draw_graph(peer_as)

                        current_burst.stop(bgp_msg.time)
                        current_burst = None

                    # Withdraw all the routes advertised by this peer
                    if global_rib_enabled:
                        for p in rib.rib:
                            send_fake_update(p, peer_ip, -1, None, None, socket)

                    peer_logger.info('Received CLOSE. CLEANING the peer.')

                    # Stop this peer
                    os.kill(os.getpid(), signal.SIGTERM)
                else:
                    peer_logger.info(bgp_msg)

                # Make sure to compute start en end time of burst with a second granularity (only if ther is a burst)
                if current_burst is not None:
                    while (last_ts != bgp_msg.time):
                        last_ts += 1

                        # Update the graph of withdraws
                        for w in W_queue.refresh_iter(last_ts):
                            current_burst.deleted_from_W_queue.append(w)

                        # Remove the current burst (if any) if it the size of the withdraws is lower than w_threshold (meaning it has finished)
                        if len(W_queue) < nb_withdrawals_burst_end: #current_burst.is_expired(bgp_msg.time):
                            # Execute BPA at the end of the burst if the burst is large enough
                            best_edge_set, best_fm_score, best_TP, best_FN, best_FP = burst_prediction(current_burst, G, G_W, W_queue, p_w, r_w, bpa_algo, peer_as_set)
                            current_burst.fd_predicted.write('PREDICTION_END|'+bpa_algo+'|'+str(len(current_burst))+'|'+str(best_fm_score)+'|'+str(best_TP)+'|'+str(best_FN)+'|'+str(best_FP)+'\n')
                            current_burst.fd_predicted.write('PREDICTION_END_EDGE|')

                            # Print some information about the prediction on the prediction file
                            res = ''
                            depth = 9999999999
                            for e in best_edge_set:
                                res += str(e[0])+'-'+str(e[1])+','
                                depth = min(G_W.get_depth(e[0], e[1]), depth)
                            current_burst.fd_predicted.write(res[:len(res)-1]+'|'+str(depth)+'\n')

                            #G_W.draw_graph(peer_as, G, current_burst, outfile='as_graph_'+str(current_burst.start_time)+'.dot', threshold=500)

                            # Update the graph of withdrawals
                            for w in current_burst.deleted_from_W_queue:
                                G_W.remove(w.as_path)

                            current_burst.stop(bgp_msg.time)
                            current_burst = None
                            break
                        else:
                            current_burst.last_ts = last_ts

                # Update the graph of withdraws.
                if current_burst is None:
                    for w in W_queue.refresh_iter(bgp_msg.time):
                        G_W.remove(w.as_path)

                # Update the last timestamp seen
                last_ts = bgp_msg.time

                # Add the updates in the real prefixes set of the burst, if any
                if current_burst is not None: #and not silent:
                    if bgp_msg.as_path != []:
                        old_as_path = bgp_msg.as_path if bgp_msg.mtype == 'W' else old_as_path
                        current_burst.add_real_prefix(bgp_msg.time, bgp_msg.prefix, bgp_msg.mtype, old_as_path)

                # If we are not in the burst yet, we create the burst
                if current_burst is None and len(W_queue) >= nb_withdrawals_burst_start:
                    current_burst = Burst(peer_id, bgp_msg.time, win_size, burst_outdir, encoding, W_queue, silent)
                    next_bpa_execution = min_bpa_burst_size

                # Print some log ...
                if (bgp_msg.time > last_log_write) or bgp_msg.time-last_log_write >= 3600:
                    peer_logger.info(str(int(bgp_msg.time))+'\t'+str(len(rib))+'\t'+str(len(W_queue)))
                    last_log_write = bgp_msg.time

                # Execute BPA if there is a burst and
                # i) the current burst is greater than the minimum required
                # ii) we have wait the number of withdrawals required per cycle or the queue is empty
                if current_burst is not None:
                    total_current_burst_size = len(current_burst)+nb_withdrawals_burst_start
                    if total_current_burst_size >= min_bpa_burst_size and total_current_burst_size > next_bpa_execution:#\
                        if nb_withdraws_per_cycle > 0 and total_current_burst_size < 12505:
                            next_bpa_execution += nb_withdraws_per_cycle
                        else:
                            next_bpa_execution = 999999999999
                        break

        #print ('Queue size: '+str(len(rib))+'\t'+str(len(W_queue))+'\t'+str(len(current_burst)+nb_withdrawals_burst_start))

        if current_burst is not None:

            # Compute the set of edges with the highest FM score
            best_edge_set, best_fm_score, best_TP, best_FP, best_FN = burst_prediction(current_burst, G, G_W, W_queue, p_w, r_w, bpa_algo, peer_as_set)
            # Load that set in the burst
            if not silent: burst_add_edge(current_burst, rib, encoding, bgp_msg.time, best_edge_set, G, G_W, W_queue, silent)

            # Inform the global RIB about the set of failed links
            for e in best_edge_set:
                depth_set = set()
                if G_W.has_edge(e[0], e[1]):
                    depth_set = depth_set.union(G_W[e[0]][e[1]]['depth'].keys())
                if G.has_edge(e[0], e[1]):
                    depth_set = depth_set.union(G[e[0]][e[1]]['depth'].keys())

                for d in depth_set:
                    if encoding.is_encoded(d, e[0], e[1]):

                            vmac_partial = ''
                            bitmask_partial = ''

                            for i in range(2, encoding.max_depth+2):
                                if i == d:
                                    vmac_partial += encoding.mapping[i].get_mapping_string(e[0])
                                    bitmask_partial += '1' * encoding.mapping[i].nb_bytes
                                elif i == d+1:
                                    vmac_partial += encoding.mapping[i].get_mapping_string(e[1])
                                    bitmask_partial += '1' * encoding.mapping[i].nb_bytes
                                else:
                                    if i in encoding.mapping:
                                        vmac_partial += '0' * encoding.mapping[i].nb_bytes
                                        bitmask_partial += '0' * encoding.mapping[i].nb_bytes

                            if global_rib_enabled:
                                socket.send('FR|'+peer_ip+'|'+vmac_partial+'|'+bitmask_partial+'|'+str(d)+'|'+str(last_ts)+'\n')

            # Print information about the perdiction in the predicted file
            current_burst.fd_predicted.write('PREDICTION|'+bpa_algo+'|'+str(len(current_burst))+'|'+str(best_fm_score)+'|'+str(best_TP)+'|'+str(best_FP)+'|'+str(best_FN)+'\n')
            current_burst.fd_predicted.write('PREDICTION_EDGE|')
            res = ''
            depth = 9999999999
            for e in best_edge_set:
                depth = min(G_W.get_depth(e[0], e[1]), depth)
                res += str(e[0])+'-'+str(e[1])+','
            current_burst.fd_predicted.write(res[:len(res)-1]+'|'+str(depth)+'\n')
