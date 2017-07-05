# SWIFT: Predictive Fast Reroute
For more information about SWIFT, please visit our [website](https://swift.ethz.ch).

## Try SWIFT

#### Run SWIFT

First,  install the following required python libraries: [blist](https://pypi.python.org/pypi/blist/?), [netaddr](https://pypi.python.org/pypi/netaddr), [networkx](https://networkx.github.io), [numpy](http://www.numpy.org).

Clone this repositery and go to the following directory
```
cd swift/main/
```

Then, just use the following command
```
python swift.py
```
###### SWIFT parameters

Several parameters can be configured to tune SWIFT:<br />
--port            Port number swift listens to receive new BGP messages (Default 3000)<br />
--win_size        Size of the sliding window (in second, default 10)<br />
--start_stop        The start and stop thresholds, separated by a comma (default 1500,9)<br />
--min_burst_size        Minimum number of withdrawals to execute BPA (default 2500, :warning: the variable triggering thresgold based on the history model (see the paper), is not available in this repositery)<br />
--bpa_freq        Frequency of BPA executions, until max 15000 withdrawals (default 2500)<br />
--p_w            Weight of PS (default 1)<br />
--r_w            Weight of WS (default 3)<br />
--bpa_algo        Algorithm to use (default bpa-multiple, can also be bpa-single or naive)<br />
--nb_bits_aspath    Number of bits reserved for the aspath compression (default 28)<br />
--nb_bits_nexthop    Number of bits reserved for each nexthop (default 3)<br />
--no_rib	Do not play the global RIB. Avoid unecessary processing, if you just need BPA results.
--silent    Silent mode. Use when you want to speed-up SWIFT. There is no debug though.

#### Feed SWIFT

Now that SWIFT is running, you need to feed it. SWIFT takes as input one or several BGP streams, as if several BGP peers were connected to SWIFT. To simulate this, you can use *run.py*, which uses the [BGPstream library](https://bgpstream.caida.org) (:warning: you must install BGPStream and its python interface pybgpstream).  

*run.py* is located in the following directory.

```
cd swift/main/feed
```

*run.py* takes the following parameters.

--dst_ip	IP address where SWIFT is running (localhost if you run SWIFT on your local machine)  
--port		Port number to use (Default 3000)  
--collectors	Collectors to use, separated by a comma (e.g. route-views.saopaulo)  
--start_time	The start timestamp  
--stop_time	The stop timestamp  
--peers_ip	List of peer IP addresses to focus on. If not indicated, all the peers of the collectors will be used  
--peers_file	File with a list of peer IP addresses to focus on. One peer IP per line.

The following example feeds SWIFT with two BGP streams from two different peers belonging to the collector route-views.saopaulo. During the timeframe, a burst of ~500K occurs on the peer 187.16.221.151.

```
python run.py --dst_ip localhost --port 3000 --collectors route-views.saopaulo --start_time 1468676128 --stop_time 1468677128 --peers_ip 187.16.221.151,187.16.220.198
```

#### SWIFT's output

###### On the standard output

SWIFT writes in the standard output the BGP messages that should be send to the SWIFTED router (Advertisements or Withdrawals). In that case, SWIFT modifies the NextHop IP address (when possible). When translated using ARP, the primary and backup nexthops as well as the as path are encoded in the MAC address. In addition, when SWIFT triggers the fast reroute process, it writes on the standard output the MAC addresses to match along with the bitmask to use (see lines with 'FR').

###### In the *bursts* directory

SWIFT writes information about the bursts found. For each burst found, SWIFT writes the real and predicted prefixes in two different files. Also, the file named *bursts_info* lists the bursts seen by SWIFT, with their size, timestamp and duration.

###### In the *log* directory

SWIFT keeps track of some debugging information when running. It helps if you want to debug.


## Try it out

We have setup a VM where a SWIFTED router can be tested and compared to a non-SWIFTED router.
In the VM are installed:
* Mininet v2.1.0
* MiniNExT
* Openvswitch v2.0.2
* Floodlight v1.1
* ExaBGP v3.4
* bgpsimple
* nmap
* Quagga
When starting the VM, you first need to built the [Quagga](http://www.nongnu.org/quagga/)-based virtual network with [miniNExT](https://github.com/USC-NSL/miniNExT), setup the different
components required for SWIFT, i.e., [openvswitch](https://github.com/openvswitch/ovs), [exabgp](https://github.com/Exa-Networks/exabgp) [floodlight](https://github.com/floodlight/floodlight), and advertise a large
set of prefixes with [bgpsimple](https://github.com/KTrel/bgpsimple).
Luckily, you can do all of this with just the following command:

```
./install.sh swift
```

If you want to try the non-SWIFTED solution, use the following command instead:

```
./install.sh noswift
```

The following figure describes the virtual network now running inside the VM if
SWIFT is used. If SWIFT is disabled, the OVS switch acts as a normal L2 switch,
and there is an eBGP session between AS2-AS3 and AS2-AS4.

![Alt text](https://github.com/nsg-ethz/swift/blob/master/vm/setup/setup.001.jpeg?raw=true "VM setup")


Each AS is a quagga router running in a Linux namespace. To access a router, you first
need to go the right namespace with *mx*. Then use *vtysh* to access the CLI of the router.
Example to access router R2:

```
./mx r2
vtysh
```

Once in the quagga CLI, feel free to look at the BGP information and the BGP routes.
Example:

```
R2# sh ip bgp summary
R2# sh ip bgp
```

When R2 has received the 200K routes (this can take few minutes, in particular
when you enable SWIFT), you can see the virtual next-hop advertised by
the SWIFT controller. When pinging one of the destination, this virtual IP next-hop
is translated into a virtual MAC address with ARP and our ARP handler running by Floodlight.

When going back to the main namespace (with *exit*, two times if you are in the quagga CLI),
you can see the Openflow rules installed the OVS switch. Simply run the following command:

```
ovs-ofctl dump-flows s1
```

The rules with a priority equal to 1000 are here to insure the normal L2 forwarding.
The rules with a priority equal to 10 are the primary rules inserted by SWIFT.
When triggering the fast-reroute process, the backup rules will be inserted by SWIFT so as
to fast reroute the affected traffic towards the right backup next-hops. Those backup
rules will have a priority of 100.

### Measure the convergence time

To measure the SWIFT convergence time, you first need to start ping measurements
from R1 towards R6.

```
./mx r1
nping --dest-ip 109.207.108.1 -H --rate 10 -c 10000
```

For clarity, this only shows the ping responses.
To simulate a remote failure, we will cut the link between R3 and R5.

```
./mx r3
ifconfig r5 down
```

At this point, the withdrawals start to be propagated and SWIFT will trigger the
fast reroute process! The convergence time is the maximum delay between two ping
responses. Example:

```
RCVD (6.4138s) ICMP [109.207.108.1 > 1.0.0.2 Echo reply (type=0/code=0) id=13615 seq=65] IP [ttl=61 id=64351 iplen=28 ]
RCVD (6.6174s) ICMP [109.207.108.1 > 1.0.0.2 Echo reply (type=0/code=0) id=13615 seq=65] IP [ttl=61 id=64353 iplen=28 ]
RCVD (6.6174s) ICMP [2.0.0.2 > 1.0.0.2 Network 109.207.108.1 unreachable (type=3/code=0) ] IP [ttl=63 id=23156 iplen=56 ]
RCVD (6.8174s) ICMP [2.0.0.2 > 1.0.0.2 Network 109.207.108.1 unreachable (type=3/code=0) ] IP [ttl=63 id=23179 iplen=56 ]
RCVD (7.6186s) ICMP [109.207.108.1 > 1.0.0.2 Echo reply (type=0/code=0) id=13615 seq=76] IP [ttl=61 id=64539 iplen=28 ]
RCVD (7.8182s) ICMP [109.207.108.1 > 1.0.0.2 Echo reply (type=0/code=0) id=13615 seq=77] IP [ttl=61 id=64559 iplen=28 ]
```

In this case, the convergence time is around 1 second.
You can do the same experiment with the non-SWIFTED router, and see the convergence
time difference.
