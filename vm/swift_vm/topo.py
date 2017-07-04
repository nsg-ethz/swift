"""
Example topology of Quagga routers
"""

import inspect
import os
from mininext.topo import Topo
from mininext.services.quagga import QuaggaService

from collections import namedtuple

QuaggaHost = namedtuple("QuaggaHost", "name ip loIP")
net = None

_THRIFT_BASE_PORT = 22222


class QuaggaTopo(Topo):

    "Creates a topology of Quagga routers"

    def __init__(self):
        """Initialize a Quagga topology with 5 routers, configure their IP
           addresses, loop back interfaces, and paths to their private
           configuration directories."""
        Topo.__init__(self)

        # Directory where this file / script is located"
        selfPath = os.path.dirname(os.path.abspath(
            inspect.getfile(inspect.currentframe())))  # script directory

        # Initialize a service helper for Quagga with default options
        quaggaSvc = QuaggaService(autoStop=False)

        # Path configurations for mounts
        quaggaBaseConfigPath = selfPath + '/configs/'

        # List of Quagga host configs
        quaggaHosts = {}
        #quaggaHosts['r1'] = (QuaggaHost(name='r1', ip='172.0.1.1/16', loIP='10.0.1.1/24'))
        quaggaHosts['r2'] = QuaggaHost(name='r2', ip='172.0.2.1/16', loIP='10.0.2.1/24')
        quaggaHosts['r3'] = QuaggaHost(name='r3', ip='172.0.3.1/16', loIP='10.0.3.1/24')
        quaggaHosts['r4'] = QuaggaHost(name='r4', ip='172.0.4.1/16', loIP='10.0.4.1/24')
        quaggaHosts['r5'] = QuaggaHost(name='r5', ip='172.0.5.1/16', loIP='10.0.5.1/24')
        #quaggaHosts['r6'] = (QuaggaHost(name='r6', ip='172.0.6.1/16', loIP='10.0.6.1/24'))


        # Add the switch for the SWIFTED router
        ovs_switch = self.addSwitch('s1', dpid='1')


        # Setup each Quagga router, add a link between it and the IXP fabric
        for name, host in quaggaHosts.iteritems():

            # Create an instance of a host, called a quaggaContainer
            quaggaContainer = self.addHost(name=host.name,
                                           ip=host.ip,
                                           hostname=host.name,
                                           privateLogDir=True,
                                           privateRunDir=True,
                                           inMountNamespace=True,
                                           inPIDNamespace=True,
                                           inUTSNamespace=True)

            # Add a loopback interface with an IP in router's announced range
            self.addNodeLoopbackIntf(node=host.name, ip=host.loIP)

            # Configure and setup the Quagga service for this node
            quaggaSvcConfig = \
                {'quaggaConfigPath': quaggaBaseConfigPath + host.name}
            self.addNodeService(node=host.name, service=quaggaSvc,
                                nodeConfig=quaggaSvcConfig)

        r6 = self.addHost(name='r6',
                               ip='172.0.6.1/16',
                               hostname='r6',
                               privateLogDir=True,
                               privateRunDir=True,
                               inMountNamespace=True,
                               inPIDNamespace=True,
                               inUTSNamespace=True)


        r1 = self.addHost(name='r1',
                              ip='172.0.1.1/16',
                              hostname='r1',
                              privateLogDir=True,
                              privateRunDir=True,
                              inMountNamespace=True,
                              inPIDNamespace=True,
                              inUTSNamespace=True)

        # Attach the quaggaContainer to the IXP Fabric Switch
        self.addLink('r1', ovs_switch, intfName1="s1", intfName2='r1-ovs')
        self.addLink('r2', ovs_switch, intfName1="s1", intfName2='r2-ovs')
        self.addLink('r3', ovs_switch, intfName1="s1", intfName2='r3-ovs')
        self.addLink('r4', ovs_switch, intfName1="s1", intfName2='r4-ovs')
