# SWIFT: Predictive Fast Reroute
For more information about SWIFT, please visit our [webiste](https://swift.ethz.ch).

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
