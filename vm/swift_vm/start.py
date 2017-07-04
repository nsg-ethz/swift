#!/usr/bin/python

"""
Example network of Quagga routers
(QuaggaTopo + QuaggaService)
"""

import sys
import atexit
import argparse

# patch isShellBuiltin
import mininet.util
import mininext.util
mininet.util.isShellBuiltin = mininext.util.isShellBuiltin
sys.modules['mininet.util'] = mininet.util

from mininet.util import dumpNodeConnections
from mininet.node import OVSController
from mininet.log import setLogLevel, info
from mininet.node import Controller, RemoteController, OVSController

from mininext.cli import CLI
from mininext.net import MiniNExT
from mininet.link import Link, TCLink

from p4_mininet.p4_mininet import P4Switch, P4Host


from topo import QuaggaTopo, QuaggaP4Topo

net = None


def startNetwork(sw_path=None, json_path=None):
    "instantiates a topo, then starts the network and prints debug information"

    info('** Creating Quagga network topology\n')
    if sw_path == None and json_path == None:
        topo = QuaggaTopo()
    else:
        topo = QuaggaP4Topo(sw_path, json_path)

    info('** Starting the network\n')
    global net
    if sw_path == None and json_path == None:
        net = MiniNExT(topo, controller=None)
    else:
        net = MiniNExT(topo, controller=None, switch=P4Switch)

    info('** Adding the controller\n')
    # Adding the remote controller
    #controller = net.addController('c1', controller=RemoteController, ip='2.0.0.4', port=6633)

    net.start()


    info('** Adding the links\n')
    # Create the full topology, including the SWIFTED router
    Link(net.getNodeByName('r1'), net.getNodeByName('r2'), intfName1='r2', intfName2='r1')
    Link(net.getNodeByName('r3'), net.getNodeByName('r5'), intfName1='r5', intfName2='r3')
    Link(net.getNodeByName('r4'), net.getNodeByName('r5'), intfName1='r5', intfName2='r4')
    Link(net.getNodeByName('r5'), net.getNodeByName('r6'), intfName1='r6', intfName2='r5')

    # Configuring host r1
    node = net.getNodeByName('r1')
    node.cmd('ifconfig r2 1.0.0.2/24')
    node.cmd('route add default gw 1.0.0.1')

    # Configuring r5 and r6
    node = net.getNodeByName('r5')
    node.cmd('/root/.disable_rp_filtering.sh')

    node = net.getNodeByName('r6')
    node.cmd('/root/.disable_rp_filtering.sh')
    node.cmd('ifconfig r5 6.0.0.2/24')
    node.cmd('ifconfig lo 109.207.108.1/24') ## CHange based on the bview R6 is advertising
    node.cmd('route add default gw 6.0.0.1')

    # Setting the right MAC addresses
    node = net.getNodeByName('r2')
    node.cmd('ip link set dev s1 address 20:00:00:00:00:01')
    node.cmd('/root/.disable_rp_filtering.sh')
    node.cmd('arp -s 2.0.0.2 20:00:00:00:00:02')
    node.cmd('arp -s 2.0.0.3 20:00:00:00:00:03')
    node.cmd('arp -s 2.0.0.4 20:00:00:00:00:04')

    node = net.getNodeByName('r3')
    node.cmd('ip link set dev s1 address 20:00:00:00:00:02')
    node.cmd('/root/.disable_rp_filtering.sh')
    node.cmd('arp -s 2.0.0.1 20:00:00:00:00:01')
    node.cmd('arp -s 2.0.0.3 20:00:00:00:00:03')
    node.cmd('arp -s 2.0.0.4 20:00:00:00:00:04')

    node = net.getNodeByName('r4')
    node.cmd('ip link set dev s1 address 20:00:00:00:00:03')
    node.cmd('/root/.disable_rp_filtering.sh')
    node.cmd('arp -s 2.0.0.1 20:00:00:00:00:01')
    node.cmd('arp -s 2.0.0.2 20:00:00:00:00:02')
    node.cmd('arp -s 2.0.0.4 20:00:00:00:00:04')

    info('** Dumping host connections\n')
    dumpNodeConnections(net.hosts)

    #info('** Testing network connectivity\n')
    #net.ping(net.hosts)

    info('** Dumping host processes\n')
    for host in net.hosts:
        host.cmdPrint("ps aux")

    info('** Running CLI\n')
    CLI(net)


def stopNetwork():
    "stops a network (only called on a forced cleanup)"

    if net is not None:
        info('** Tearing down Quagga network\n')
        net.stop()

if __name__ == '__main__':

    parser = argparse.ArgumentParser("Run MiniMExT with P4 targets.")
    parser.add_argument("--sw_path", type=str, default=None, help="Path where to find the switch target.")
    parser.add_argument("--json_path", type=str, default=None, help="Path where to find the json P4 program.")
    args = parser.parse_args()
    sw_path = args.sw_path
    json_path = args.json_path

    print sw_path
    print json_path

    # Force cleanup on exit by registering a cleanup function
    atexit.register(stopNetwork)

    # Tell mininet to print useful information
    setLogLevel('info')
    startNetwork(sw_path, json_path)
