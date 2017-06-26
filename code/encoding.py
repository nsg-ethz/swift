import os, shutil
from blist import sortedlist
from blist import sortedset
import timeit
import numpy as np

class Mapping:

    def __init__(self):
        self.nb_bytes = 0

        # Initialize the set of free values (Initaly all the values are free)
        self.free = sortedset()

        # A dictionnary used to store the mapping AS to integer. An other value
        # is also used to indicate how many times each AS appear on this mapping.
        self.mapping = {}

        self.blocked = False
        self.max_free = 500

    ###
    # @brief    This function adds an AS number in the mapping. In case there is
    #           mapping available, this function adds new value in the free set.
    #
    # @param    asn     AS number
    #
    # @return   Boolean: True if AS number have been added, False if the AS was
    #           already in the mapping
    ###
    def add(self, asn, from_as=True, overprovisioning=True):
        res = 0

        if asn not in self.mapping:

            if len(self.free) == 0:
                if self.blocked == True:
                    return -1, False
                else:
                    self.add_byte()
                    res += 1

            if overprovisioning:
                if len(self.free) <= len(self.mapping) and len(self.free) < self.max_free:
                    if self.blocked:
                        return -1, False
                    else:
                        self.add_byte()
                        res += 1

            if from_as:
                self.mapping[asn] = [self.free[0], 1, 0]
            else:
                self.mapping[asn] = [self.free[0], 0, 1]

            self.free.pop(0)

            return res, True

                #if overprovisioning and len(self.free) < len(self.mapping) and len(self.free) < 1500: # To ensure overprovisioning if needed

        else:
            if from_as:
                self.mapping[asn][1] += 1
            else:
                self.mapping[asn][2] += 1

        return 0, False

    ###
    # @brief        This functions how many new bits are required to add a new asn
    #               in the mapping. It can consider overprovisioning,
    #               and also an additional offset.
    #
    # @param        asn     The AS number we would to check availbility
    # @param overprovisioning Boolean. True if we do overprovisioning
    # @param        offset  In addition to overprovisioning, we can add an offset
    #
    # @return       Returns the number of bit required to sote this asn in this mapping.
    #               i.e. 0 means no additional bit are required
    ###
    def is_available(self, asn, overprovisioning=True, offset=0):
        if asn not in self.mapping:
            if overprovisioning:
                if not (len(self.free)-offset > len(self.mapping)+offset or len(self.free)-offset > self.max_free):
                    if self.nb_bytes == 0:
                        return 2
                    else:
                        return 1
                else:
                    return 0
            else:
                if len(self.free)-offset > 0:
                    return 0
                else:
                    return 1
        else:
            return 0


    def add_byte(self):
        if self.nb_bytes == 0:
            #self.free.add(0)
            # Set the mapping for 0, which is used to match an AS link that is not encoded
            self.mapping[-1] = [0, -1, -1]

        self.nb_bytes += 1
        for i in range(pow(2, self.nb_bytes-1), pow(2, self.nb_bytes)):
            self.free.add(i)

    ###
    # @brief    This function   removes the AS number from the mapping.
    #
    # @param    asn     AS number.
    ###
    def remove(self, asn, from_as=True):
        if asn in self.mapping:
            if from_as:
                self.mapping[asn][1] -= 1
            else:
                self.mapping[asn][2] -= 1

            if self.mapping[asn][1] < 0 or self.mapping[asn][2] < 0:
                sys.exit(0)

            if self.mapping[asn][1] == 0 and self.mapping[asn][2] == 0:
                tmp = self.mapping[asn]
                del self.mapping[asn]
                self.free.add(tmp[0])

                return True
        return False

    def get_mapping_string(self, asn):
        if asn in self.mapping:
            res = bin(self.mapping[asn][0])[2:]
            return res.zfill(self.nb_bytes)
        else:
            return '0' * self.nb_bytes

    def __str__(self):
        tmp = str(self.nb_bytes)+' Free '
        for i in self.free:
            tmp += str(i)+','
        tmp += ' '
        tmp += 'Mapping '
        for k, v in self.mapping.items():
            tmp += str(k)+'>'+str(v)+','

        return tmp


class Encoding():

    def __init__(self, peer_id, topo, outdir, max_bytes, min_percentile, traffic_w=0.6, output=True):
        self.peer_id = peer_id
        self.mapping = {}   # One mapping for each depth
        self.outdir = outdir
        self.minimum = {}   # One minimum for each depth
        self.max_bytes = max_bytes
        self.g = topo
        self.min_percentile = min_percentile
        self.encoded_aslinks = {}   # AS links encoded for each depth

        # Use to compute the weighted sum for each as link
        self.total_traffic = {}
        self.total_prefixes = {}
        self.traffic_w = traffic_w

        # Optimisations
        self.opti_bits = False

        # Ouput enabled/disabled
        self.output = output

        # Create the directory if it does not exist
        if not os.path.exists('encoding'):
            os.makedirs('encoding')
        if output:
            self.fd_peer = open(self.outdir+'/'+peer_id, 'w', 10)

        self.max_depth = 4

    def compute_sortedlist(self, depth_wanted=None):

        sortedlist_depth = {}

        for from_node in self.g:
            for to_node in self.g[from_node].keys():
                for depth, nb_prefixes in self.g[from_node][to_node]['depth'].items():

                    if (depth_wanted is None and depth > 1 and depth <= self.max_depth) or \
                    (depth_wanted is not None and depth in depth_wanted and depth > 1 and depth <= self.max_depth):
                        if depth not in sortedlist_depth:
                            sortedlist_depth[depth] = sortedlist()

                        sortedlist_depth[depth].add([nb_prefixes, from_node, to_node])

        return sortedlist_depth

    """
    This function computes a static encoding. It optimizes the number of bits
    available to store the most important edges. Used to initialize the encoding.
    """
    def compute_encoding(self):

        start = timeit.default_timer()

        # Create a dictionnary with a pointer on the highest as link (the one on
        # the right side of the list) for each depth.
        aslink_sortedlist_depth = self.compute_sortedlist()

        minimum_tmp = {}
        self.encoded_aslinks = {}
        for depth in aslink_sortedlist_depth.keys():
            self.encoded_aslinks[depth] = set()
            minimum_tmp[depth] = []

        self.mapping = {}
        total_bytes = 0

        while True:
            next = None
            depth = 0

            # Find which as link has the highest metric
            for d, aslink in aslink_sortedlist_depth.items():
                if len(aslink) == 0:
                    continue
                elif next is None:
                    next = aslink
                    depth = d
                elif aslink[-1][0] > next[-1][0]:
                    # If more prefixes traverse this edge and if a failure can make a burst
                    next = aslink
                    depth = d

            # In case all the aslink are in the mapping (should never happen with a full Internet routing table)
            if next is None:
                while total_bytes < self.max_bytes-2:
                    to_increase = None
                    for d, dmap in self.mapping.items():
                        if to_increase is None or len(to_increase.free) > len(dmap.free):
                           to_increase = dmap

                    if to_increase is None:
                        break
                    else:
                        to_increase.add_byte()
                        total_bytes += 1
                break

            else:

                # Update the mapping accordingly
                if depth not in self.mapping:
                    self.mapping[depth] = Mapping()
                if depth+1 not in self.mapping:
                    self.mapping[depth+1] = Mapping()

                bytes_to_add = self.mapping[depth].is_available(next[-1][1], overprovisioning=True, offset=0)
                bytes_to_add += self.mapping[depth+1].is_available(next[-1][2], overprovisioning=True, offset=0) #### CHECK THE OFFSET HERE

                # If we cannot add this AS link in the encodage, we go to the next iteration
                if total_bytes + bytes_to_add <= self.max_bytes-2:
                    min_pref = next[-1][0]

                    tmp1 = self.mapping[depth].add(next[-1][1], True)[0]
                    if tmp1 >= 1:
                        total_bytes += tmp1
                    tmp2 = self.mapping[depth+1].add(next[-1][2], False)[0]
                    if tmp2 >= 1:
                        total_bytes += tmp2

                    self.encoded_aslinks[depth].add((next[-1][1], next[-1][2]))

                    if total_bytes >= self.max_bytes-2:
                        self.mapping[depth].blocked = True
                        self.mapping[depth+1].blocked = True

                    # Refresh the minimum weight*traffic for this peer and this depth
                    minimum_tmp[depth].append(next[-1][0])

                # Refresh the dictionnary with the pointers towards the highest as links
                # for each depth
                next.pop()

        # Add one more bit in the second depth (the more critical one)
        if 2 in self.mapping:
            #self.mapping[2].add_byte()
            self.mapping[2].add_byte()
        if 3 in self.mapping:
            self.mapping[3].add_byte()

        # Compute the minimum weight*traffic required for a link to be added in
        # the encoding in the future
        self.minimum = {}
        for depth, vec in minimum_tmp.items():
            if len(vec) > 0:
                self.minimum[depth] = np.percentile(vec, self.min_percentile)

        stop = timeit.default_timer()
        self.print_debug('C|'+str(stop - start)+'\n')
        self.print_status(prefix='C')

    ###
    # @brief    This function adds an AS link in the encodage if its total weight
    #           is high enough for the speficied depth.
    #
    # @param    peer_ip                 Peer IP address.
    # @param    depth                   Depth in the AS path.
    # @param    prev_as                 From AS.
    # @param    next_as                 To AS.
    #
    # @return   Boolean, True means that an AS have been added in the
    #           encodage, otherwise False.
    ###
    def add(self, depth, prev_as, next_as):
        if depth in self.mapping and depth+1 in self.mapping and depth in self.minimum:
            # If the link has not been encoded yet
            if prev_as not in self.mapping[depth].mapping or next_as not in self.mapping[depth+1].mapping:

                # In case the capacity is full for the depth(s), we refresh the encoding
                if len(self.mapping[depth].free) == 0:
                    self.refresh(depth)
                if len(self.mapping[depth+1].free) == 0:
                    self.refresh(depth+1)

                m = self.g[prev_as][next_as]['depth'][depth]
                if self.minimum[depth] < m:

                    can_be_added = True
                    if prev_as not in self.mapping[depth].mapping:
                        if self.mapping[depth].is_available(prev_as, overprovisioning=False, offset=0) > 0:
                            can_be_added = False
                    if next_as not in self.mapping[depth+1].mapping:
                        if self.mapping[depth+1].is_available(next_as, overprovisioning=False, offset=0) > 0:
                            can_be_added = False

                    if can_be_added:
                        p, added_p = self.mapping[depth].add(prev_as, from_as=True, overprovisioning=False)
                        n, added_n = self.mapping[depth+1].add(next_as, from_as=False, overprovisioning=False)
                        self.encoded_aslinks[depth].add((prev_as, next_as))
                        if added_p == 1 or added_n == 1:
                            return True
                        else:
                            return False

        return False

    """
    Removes an edge from the encoding, and returns the overhead this operation added
    in the controle plane (in terms of number of additional bgp prefix updates).
    Info: Removing an edge does not necessarily release space in the encoding.
    Indeed, the space can still be used by other edges, still encoded.
    """
    def remove(self, depth, prev_as, next_as):
        control_plane_overhead = 0
        if depth in self.mapping and depth+1 in self.mapping:
            if (prev_as, next_as) in self.encoded_aslinks[depth]:
                p = self.mapping[depth].remove(prev_as, True)
                n = self.mapping[depth+1].remove(next_as, False)
                self.encoded_aslinks[depth].remove((prev_as, next_as))

                try:
                    control_plane_overhead = self.g[prev_as][next_as]['depth'][depth]
                except KeyError:
                    pass
        return control_plane_overhead

    """
    Refresh the encodage upon reception of the prefix advertisement.
    Two steps are done: i) remove edges in the encodage if no prefixe traverse them anymore
                        ii) add the new edges in the encoding it their number of prefixes
                        traversing them are higher than the minimum threshold
    In case no space is available anymore in the encoding, a refresh is done on
    the required depth to store only the most important edges.
    """
    def advertisement(self, old_aspath, new_aspath):
        self.withdraw(old_aspath)

        for i in range(0, len(new_aspath)-1):
            self.add(i+1, new_aspath[i], new_aspath[i+1])

    """
    Remove edges in the encodage if no prefixes traverse it anymore (and only in that case)
    """
    def withdraw(self, old_aspath):
        for i in range(0, len(old_aspath)-1):
            # Remove the edge from the encoding if this edge is not used anymmore
            if not self.g.has_edge(old_aspath[i], old_aspath[i+1]) or i+1 not in self.g[old_aspath[i]][old_aspath[i+1]]['depth']:
                self.remove(i+1, old_aspath[i], old_aspath[i+1])

        #self.print_status(prefix='INFO')

    """
    Refresh a mapping for a depth. This function is called when a mapping is full.
    This function releases some space in the mapping for the depth. It removes the less
    important edges in the encoding. At the end, 50% of the sapce is used, and 50% is
    available.
    """
    def refresh(self, depth_targeted):
        control_plane_overhead = 0

        self.print_status(prefix='BR')

        # To refresh the mapping at depth X, we can remove edges at depth X-1 or X.
        aslink_sortedlist_depth = self.compute_sortedlist(set([depth_targeted-1, depth_targeted]))

        # Re initialize the minimum treshold
        minimum_tmp = {}
        for depth, slist in aslink_sortedlist_depth.items():
            minimum_tmp[depth] = []

        while True:
            next = None
            depth = 0

            # Find which as link has the highest (lowest in this case) metric
            for d, aslink in aslink_sortedlist_depth.items():
                if len(aslink) == 0:
                    continue
                elif next is None:
                    next = aslink
                    depth = d
                else:
                    nb_bytes_cur_from = 0 if d not in self.mapping else self.mapping[d].nb_bytes
                    nb_bytes_cur_to = 0 if d+1 not in self.mapping else self.mapping[d+1].nb_bytes
                    nb_bytes_best_from = 0 if depth not in self.mapping else self.mapping[depth].nb_bytes
                    nb_bytes_best_to = 0 if depth+1 not in self.mapping else self.mapping[depth+1].nb_bytes

                    if self.opti_bits:
                        if aslink[0][0]*pow(2, nb_bytes_cur_from) + aslink[0][0]*pow(2, nb_bytes_cur_to) < next[0][0]*pow(2, nb_bytes_best_from) + next[0][0]*pow(2, nb_bytes_best_to):
                            next = aslink
                            depth = d
                    else:
                        if aslink[0][0] < next[0][0]:
                            next = aslink
                            depth = d

            # In case all the aslink are in the mapping (should never happen with a full Internet routing table)
            if next is None:
                break
            else:
                # If more than hald of the space os used at that depth, we try to remove this edge
                if len(self.mapping[depth_targeted].mapping) > pow(2, self.mapping[depth_targeted].nb_bytes-1):
                    control_plane_overhead += self.remove(depth, next[0][1], next[0][2])
                # Otherwise, refresh the array used to compute the minimum threshold
                else:
                    # Only if the edge is encoded though
                    if depth in self.encoded_aslinks and (next[0][1], next[0][2]) in self.encoded_aslinks[depth]:
                        minimum_tmp[depth].append(next[0][0])
                next.pop(0)

        for depth, vec in minimum_tmp.items():
            if len(vec) > 0:
                self.minimum[depth] = np.percentile(vec, self.min_percentile)

        self.print_status(prefix='AR', suffix=str(control_plane_overhead))

    """
    Returns a boolean indicating if an edge, at a specific depth, is encoded.
    """
    def is_encoded(self, depth, from_as, to_as):
        if depth == 1:
            if depth+1 in self.mapping:
                return to_as in self.mapping[depth+1].mapping
            else:
                return False
        else:
            if depth in self.encoded_aslinks:
                if (from_as, to_as) in self.encoded_aslinks[depth]:
                    return True
            else:
                return False

    """
    Based on the fact that BPA predited the edge (from_as, to_as) has failed,
    can the prefix be rerouted? i.e. Is this edge encoded at the right for this prefix?
    """
    def prefix_is_encoded(self, prefix, aspath, from_as, to_as):
        cur_depth = 1
        for i in range(0, len(aspath)):
            if aspath[i] == from_as and aspath[i+1] == to_as:
                return self.is_encoded(cur_depth, from_as, to_as), cur_depth
            cur_depth += 1

        print 'Error: encoding.py prefix_is_encoded'
        return False, -1

    def print_debug(self, string):
        if self.output:
            self.fd_peer.write(string)

    def print_status(self, prefix='A', suffix=''):
        if self.output:
            tmp = prefix+'|'
            for key, value in self.mapping.items():
                if key > 1:
                    if value.nb_bytes > 0:
                        tmp += str(len(value.mapping))+'/'+str(pow(2, value.nb_bytes))+'|'
                    else:
                        tmp += '0/0|'
            tmp += suffix
            tmp += '\n'

            self.fd_peer.write(tmp)


if __name__ == '__main__':
    m = Mapping ()
    m.add(1, True)
    print m
    m.add(2, True)
    print m
    print m.is_available(3)
    m.add(3, True)
    print m
    print m.is_available(4, offset=0)
    m.add(4, True)
    print m
    print m.is_available(5, )
    m.add(5, True)
    print m
    print m.is_available(6, offset=2)
    m.add(6, True)
    m.add(7, True)
    m.add(8, True)
    print m
