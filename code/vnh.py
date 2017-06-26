from netaddr import *
import string
import re
import os
from collections import deque

class VirtualNextHops:

    def __init__(self, rib, nexthops_nb_bits=3, pusher=None, switch_dpid=None, \
    IP_prefix="2.0.0.128/25", vnh_file="virtual_nexthops", mapping_router='mapping', logger=None):

        # The Routing Information Base
        self.rib = rib

        # Logger from the global rib
        self.logger = logger

        # Mapping next Real IP to Tag in the MAC address
        self.tag_dic = {}

        # The number of bits we allocate for a nexthop
        self.nexthops_nb_bits = nexthops_nb_bits

        # The max link depth
        self.max_depth = 4

        # Dictionnary used to store the pair of virtual MAC and IP addresses.
        # Key: Mac addresses; Value: IP addresses
        self.VNH_pair = {}

        # File where to write the mapping nexthop IP/MAC address
        self.vnh_file = open(vnh_file, 'w', 1)

        # Generate the set of virtual IP addresses
        self.VNH_IP_prefix = int(IPNetwork(IP_prefix).network)
        self.counter = 0

        # Mapping Real IP NextHop to (real MAC and output port)
        try:
            self.mapping_real = {}
            fd_tmp = open(mapping_router, 'r')
            for line in fd_tmp.readlines():
                linetab = line.split()
                self.mapping_real[linetab[0]] = (linetab[1], linetab[2].rstrip('\n'))
            fd_tmp.close()
        except:
            self.logger.warning('VNH: Mapping file not available')

        self.fd_rules = open('switch_rules', 'w', 1)

    def get_VNH(self, prefix):
        if len(self.rib.rib[prefix]) < 2:
            # If only one route is available for this prefix, return the real NextHop IP address
            if len(self.rib.rib[prefix]) > 0:
                return self.rib.rib[prefix][0].peer_ip, None
            else: # If no routes is available, return None
                return None, None
        else:
            # Create the mapping for the primary NextHop and create the virtual MAC
            primary_ip = self.rib.rib[prefix][0].peer_ip
            if primary_ip not in self.tag_dic:
                tag = len(self.tag_dic)
                self.tag_dic[primary_ip] = tag
                self.insert_primary_rules(primary_ip)

            primary_nh = bin(self.tag_dic[primary_ip])[2:]
            primary_nh = primary_nh.zfill(self.nexthops_nb_bits)
            v_mac = primary_nh

            # Build the VMAC for the backup NH
            as_path = self.rib.rib[prefix][0].as_path
            for d in range(0, min(len(as_path)-1, self.max_depth)):
                backup_ip = self.rib.get_backup_avoiding_aslink(primary_ip, prefix, (as_path[d], as_path[d+1])).peer_ip

                if backup_ip not in self.tag_dic:
                    tag = len(self.tag_dic)
                    self.tag_dic[backup_ip] = tag
                    self.insert_primary_rules(backup_ip)

                backup_nh = bin(self.tag_dic[backup_ip])[2:]
                backup_nh = backup_nh.zfill(self.nexthops_nb_bits)

                v_mac = v_mac+''+backup_nh

            v_mac = string.ljust(v_mac, self.nexthops_nb_bits*(self.max_depth+1), '0')

            v_mac += '.'+self.rib.rib[prefix][0].partial_vmac

            if v_mac not in self.VNH_pair:
                self.counter += 1
                vmac_floodlight = int(v_mac.replace('.', ''), 2)

                self.VNH_pair[v_mac] = IPAddress(self.VNH_IP_prefix+self.counter)
                self.vnh_file.write(str(self.VNH_pair[v_mac])+'\t'+str(vmac_floodlight)+'\t'+v_mac+'\n')

            return self.VNH_pair[v_mac], v_mac

    def insert_primary_rules(self, primary_ip):
        primary_tag = self.tag_dic[primary_ip]
        tmp_mac = bin(primary_tag)[2:]
        tmp_mac = tmp_mac.zfill(self.nexthops_nb_bits)

        tmp_mac = string.ljust(tmp_mac, 48, '0')

        bitmask = string.ljust('', self.nexthops_nb_bits, '1')
        bitmask = string.ljust(bitmask, 48, '0')

        try:
            real_mac = self.mapping_real[primary_ip][0]
            outport = self.mapping_real[primary_ip][1]
        except KeyError:
            real_mac = 'unknown'
            outport = 'unknown'

        # Binary to Hexadecimal conversion
        tmp_mac = hex(int(tmp_mac, 2))[2:].zfill(12)
        bitmask = hex(int(bitmask, 2))[2:].zfill(12)

        tmp_mac = ':'.join(s.encode('hex') for s in tmp_mac.decode('hex'))
        bitmask = ':'.join(s.encode('hex') for s in bitmask.decode('hex'))

        self.fd_rules.write('ovs-ofctl add-flow s1 priority=10,dl_dst='+tmp_mac+'/'+bitmask+',actions=mod_dl_dst:'+real_mac+',output:'+outport+'\n')
        os.system('ovs-ofctl add-flow s1 priority=10,dl_dst='+tmp_mac+'/'+bitmask+',actions=mod_dl_dst:'+real_mac+',output:'+outport)

    def insert_backup_rules(self, peer_ip, depth, aspath_vmac, aspath_bitmask):
        final_flows = []

        for backup_ip in self.tag_dic:
            if backup_ip != peer_ip:

                # Build the part reserved for the primary nexthop
                primary_tag = self.tag_dic[peer_ip]
                backup_vmac = bin(primary_tag)[2:]
                backup_vmac= backup_vmac.zfill(self.nexthops_nb_bits)
                # Update the bitmask accordingly
                backup_bitmask = '1' * self.nexthops_nb_bits

                for i in range(1, self.max_depth+1):
                    if i == depth:
                        backup_tag = self.tag_dic[backup_ip]
                        backup_vmac += bin(backup_tag)[2:].zfill(self.nexthops_nb_bits)

                        backup_bitmask += '1' * self.nexthops_nb_bits

                    else:
                        backup_vmac += '0' * self.nexthops_nb_bits
                        backup_bitmask += '0' * self.nexthops_nb_bits

                try:
                    real_mac = self.mapping_real[backup_ip][0]
                    outport = self.mapping_real[backup_ip][1]
                except KeyError:
                    real_mac = 'unknown'
                    outport = 'unknown'

                print 'FR|'+backup_vmac+','+aspath_vmac+'|'+backup_bitmask+','+aspath_bitmask#+'|'+str(real_mac)+'|'+str(outport)

                self.fd_rules.write('ovs-ofctl add-flow s1 priority=100,dl_dst='+backup_vmac+aspath_vmac+'/'+backup_bitmask+aspath_bitmask+',actions=mod_dl_dst:'+real_mac+',output:'+outport+'\n')

                tmp_mac = hex(int(backup_vmac+aspath_vmac, 2))[2:].zfill(12)
                bitmask = hex(int(backup_bitmask+aspath_bitmask, 2))[2:].zfill(12)

                tmp_mac = ':'.join(s.encode('hex') for s in tmp_mac.decode('hex'))
                bitmask = ':'.join(s.encode('hex') for s in bitmask.decode('hex'))

                final_flows.append('dl_dst='+tmp_mac+'/'+bitmask)

                os.system('ovs-ofctl add-flow s1 priority=100,dl_dst='+tmp_mac+'/'+bitmask+',actions=mod_dl_dst:'+real_mac+',output:'+outport)

        return final_flows

    def __str__(self):
        res = ''
        for mac, ip in self.VNH_pair.items():
            res += mac+'\t'+str(ip)+'\n'
        return res

""" Tuples (timestamp, OF flow) are inserted in this queue"""
class FlowsQueue(deque):
    def __init__(self, time):
        super(FlowsQueue, self).__init__()
        self.time = time

    """
    Remove all the bgp messages in the queue that have expired
    """
    def refresh(self, ts):
        while len(self) > 0 and ts - self[0][0] > self.time:
            self.popleft()

    """
    Remove all the bgp messages in the queue that have expired.
    And yields the expired messages.
    """
    def refresh_iter(self, ts):
        while len(self) > 0 and ts - self[0][0] > self.time:
            yield self.popleft()[1]
