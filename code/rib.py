import sys
import os
import select
import logging
import logging.handlers
import signal
import cPickle as pickle
from bgproute import BGPRoute
from rib_global import RIBGlobal
import atexit
import time
from vnh import VirtualNextHops, FlowsQueue

class RIBPeer:
    def __init__(self):
        self.rib = {}

    """
    Update (or create) the AS path for a prefix and returns the previous AS path used
    """
    def update(self, bgp_msg):
        if bgp_msg.prefix in self.rib:
            as_path = self.rib[bgp_msg.prefix]
        else:
            as_path = []
        self.rib[bgp_msg.prefix] = bgp_msg.as_path

        return as_path

    """
    Delete this prefix, and returns the last AS path known for this prefix
    """
    def withdraw(self, bgp_msg):
        if bgp_msg.prefix in self.rib:
            as_path = self.rib[bgp_msg.prefix]
            del self.rib[bgp_msg.prefix]
            return as_path
        else:
            return []

    def __len__(self):
        return len(self.rib)

    def __str__(self):
        res = ''
        for i in self.rib:
            res += str(i)+'\t'+str(self.rib[i])+'\n'
        return res

# Parameters used for the loggers
rib_logger = None

# Initialize the main peer logger
def rib_init_logger(logdir_name):
    global rib_logger

    rib_logger_loc = logging.getLogger('RibLogger')
    rib_logger_loc.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s')
    handler = logging.handlers.RotatingFileHandler(logdir_name+'/rib', maxBytes=200000000000000, backupCount=5)
    handler.setFormatter(formatter)
    rib_logger_loc.addHandler(handler)

    rib_logger_loc.info('RIB launched!')
    rib_logger = rib_logger_loc


def rib_global(port, nb_bits_nexthop, dirname, socket_rib_name):
    import socket

    try:
        os.nice(-20)
    except OSError:
        rib_logger.info('Cannot change the nice.')

    rib_global_socket_address = '/tmp/'+socket_rib_name
    # Make sure the socket does not already exist
    try:
        os.unlink(rib_global_socket_address)
    except OSError:
        if os.path.exists(rib_global_socket_address):
            raise

    socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    socket.bind(rib_global_socket_address)
    socket.listen(5)

    # Exit properly when receiving SIGINT
    def signal_handler(signal, frame):
        rib_logger.info('Received SIGTERM. Exiting.')

        # Deleting all the backup flows
        for ts, f in OFFlowsQueue:
            with open('deleted_rules', 'a') as fd_del:
                fd_del.write(f+'\n')
            os.system('ovs-ofctl del-flows s1 '+f)

        socket.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)

    def exit_handler():
        socket.close()
    atexit.register(exit_handler)

    # The Global RIB
    rib_global = RIBGlobal()

    # The virtual nexthops handler
    vnh = VirtualNextHops(rib_global, nb_bits_nexthop, logger=rib_logger)

    OFFlowsQueue = FlowsQueue(60*5) # Backup rules deleted after 5 minutes

    sock_list = [socket]
    data_dic = {}

    while True:

        inready, outready, excepready = select.select (sock_list, [], [])

        for sock in inready:
            if sock == socket:
                (newsock, address) = sock.accept()
                sock_list.append(newsock)
                data_dic[newsock] = ''
                rib_logger.info('New connection from '+str(address))
            else:
                data_tmp = sock.recv(100000000)

                if len(data_tmp) == 0:
                    rib_logger.info('One peer has Disconnected')
                    sock.close()
                    sock_list.remove(sock)

                else:
                    data_dic[sock] += data_tmp

                    next_data = ''
                    while data_dic[sock][-1] != '\n':
                        next_data = data_dic[sock][-1]+next_data
                        data_dic[sock] = data_dic[sock][:-1]

                    """ In case the peer wants to fast reroute"""
                    for data_line in data_dic[sock].rstrip('\n').split('\n'):
                        if data_line.startswith('FR'):
                            data_line_tab = data_line.split('|')
                            peer_ip = data_line_tab[1]
                            vmac_partial = data_line_tab[2]
                            bitmask_partial = data_line_tab[3]
                            depth = int(data_line_tab[4])
                            ts = int(float(data_line_tab[5]))

                            for f in vnh.insert_backup_rules(peer_ip, depth, vmac_partial, bitmask_partial):
                                OFFlowsQueue.append((ts, f))

                        else:
                            data_line_tab = data_line.split('|')
                            peer_ip = data_line_tab[0]
                            prefix = data_line_tab[1]
                            ts = float(data_line_tab[2])

                            for f in OFFlowsQueue.refresh_iter(ts):
                                with open('deleted_rules', 'a') as fd_del:
                                    fd_del.write(f+'\n')
                                os.system('ovs-ofctl del-flows s1 '+f)

                            """ In case it is an advertisement """
                            if len(data_line_tab) == 5:
                                v_mac = data_line_tab[4]

                                if len(data_line_tab[3]) > 0:
                                    try:
                                        as_path = map(lambda x:int(x), data_line_tab[3].split(' '))
                                    except:
                                        print data_line_tab
                                        as_path = []
                                else:
                                    as_path = []
                                bgproute = BGPRoute(prefix, peer_ip, as_path, v_mac)
                                prev_prim, new_prim, bgproute, prev_backup, new_backup = rib_global.announce(bgproute)

                                vnh_ip, vnh_mac = vnh.get_VNH(prefix)
                                print 'A|'+str(prefix)+'|'+str(vnh_ip)+'|('+str(vnh_mac)+')|'+str(' '.join(map(lambda x:str(x), new_prim.as_path)))

                                """ In case it is a withdrawal """
                            else:
                                prev_prim, new_prim, bgproute, prev_backup, new_backup = rib_global.withdraw(peer_ip, data_line_tab[1])

                                if new_prim is not None:
                                    vnh_ip, vnh_mac = vnh.get_VNH(prefix)
                                    print 'A|'+str(prefix)+'|'+str(vnh_ip)+'|('+str(vnh_mac)+')|'+str(' '.join(map(lambda x:str(x), new_prim.as_path)))
                                else:
                                    if prev_prim is not None:
                                        print 'W|'+str(prefix)

                    data_dic[sock] = next_data
