from blist import sortedset
from bgproute import BGPRoute

class RIBGlobal:

    def __init__(self):
        self.rib = {}
        self.rib_peer = {}

    ###
    # @brief    This function processes an advertisement. It refreshes the rib
    #           and rib_peer accordingly.
    #
    # @param    bgproute        The BGPRoute advertised
    #
    # @return   The new BGPRoute used to reach the prefix announced
    #           along with the previous BGPRoute used to reach that prefix.
    #           If no BGPRoute existed for this prefix before the announcement,
    #           None is returned as the previous BGPRoute. Additional information
    #           is returned for SWIFT.
    ###
    def announce(self, bgproute):
        # In case this prefix was not advertised before
        if bgproute.prefix not in self.rib:
            self.rib[bgproute.prefix] = sortedset()
            previous_BGPRoute = None
        else:
            previous_BGPRoute = self.rib[bgproute.prefix][0]

        # Get the second best route, for the virtual MAC address encoding
        if len(self.rib[bgproute.prefix]) > 1:
            previous_backup_BGPRoute = self.rib[bgproute.prefix][1]
        else:
            previous_backup_BGPRoute = None

        # In case this peer advertised this prefix already
        previous_BGPRoute_peer = None
        if bgproute.peer_ip in self.rib_peer:
            if bgproute.prefix in self.rib_peer[bgproute.peer_ip]:
                previous_BGPRoute_peer = self.rib_peer[bgproute.peer_ip][bgproute.prefix]
                self.rib[bgproute.prefix].remove(previous_BGPRoute_peer)
        # In case the peer is new (its the first advertisement)
        else:
            self.rib_peer[bgproute.peer_ip] = {}

        # Add the new bgproute in the rib
        self.rib[bgproute.prefix].add(bgproute)
        # Refresh (or initialize) the rib_peer structure
        self.rib_peer[bgproute.peer_ip][bgproute.prefix] = bgproute

        new_BGPRoute = self.rib[bgproute.prefix][0]

        # Get the second best route, for the virtual MAC address encoding
        if len(self.rib[bgproute.prefix]) > 1:
            new_backup_BGPRoute = self.rib[bgproute.prefix][1]
        else:
            new_backup_BGPRoute = None

        return previous_BGPRoute, new_BGPRoute, previous_BGPRoute_peer, previous_backup_BGPRoute, new_backup_BGPRoute


    ###
    # @brief    This function processes a withdraw. It refreshes the rib and
    #           and rib_peer accordingly and returns the BGProute object that
    #           have been withdrawn.
    #
    # @param    peer_ip     IP address of the peer sending this withdraw
    # @param    prefix      Prefix that is withdrawn
    #
    # @return   A tuple with the new BGPRoute used to follow to reach the prefix announced
    #           along with the previous BGPRoute used to follow to reach the prefix.
    #           If no BGPRoute exists for this prefix after (or before?) the
    #           withdraw, None is returned as the previous BGPRoute.
    ###
    def withdraw(self, peer_ip, prefix):
        # Get the corresponding BGPRoute from the rib_peer
        if peer_ip in self.rib_peer and prefix in self.rib_peer[peer_ip]:
            bgproute = self.rib_peer[peer_ip][prefix]
        else:
            return None, None, None, None, None

        # Get the second best route, for the virtual MAC address encoding
        if len(self.rib[bgproute.prefix]) > 1:
            previous_backup_BGPRoute = self.rib[bgproute.prefix][1]
        else:
            previous_backup_BGPRoute = None

        # Get the previous best BGPRoute for the prefix withdrawn
        if prefix in self.rib:
            previous_BGPRoute = self.rib[prefix][0]
        else:
            previous_BGPRoute = None

        # Remove the BGRoute from the rib
        self.rib[prefix].remove(bgproute)
        if len(self.rib[prefix]) == 0:
            del self.rib[prefix]

        # Get the new best BGPRoute
        if prefix in self.rib:
            new_BGPRoute = self.rib[prefix][0]
        else:
            new_BGPRoute = None

        # Refresh the rib_peer structure
        del self.rib_peer[peer_ip][prefix]
        if len(self.rib_peer[peer_ip]) == 0:
            del self.rib_peer[peer_ip]

        # Get the second best route, for the virtual MAC address encoding
        if bgproute.prefix in self.rib and len(self.rib[bgproute.prefix]) > 1:
            new_backup_BGPRoute = self.rib[bgproute.prefix][1]
        else:
            new_backup_BGPRoute = None

        return previous_BGPRoute, new_BGPRoute, bgproute, previous_backup_BGPRoute, new_backup_BGPRoute

    # Remove all the routes advertised by a peer
    ### NOT USED, NOT TESTED
    """def clean_peer(self, peer_ip):
        for p in self.rib:
            cur_index = 1
            for bgproute in self.rib[p]:
                if bgproute.peer_ip == peer_ip:

                    # Compute the best and backup routes before removing the route from the peer_ip
                    if cur_index == 1 or cur_index == 2:
                        previous_BGPRoute = self.rib[p][0]
                        if len(self.rib[p]) > 1:
                            previous_backup_BGPRoute = self.rib[p][1]

                    self.rib[p].remove(bgproute)

                    # Compute the best and backup routes after removing the route from the peer_ip
                    if cur_index == 1 or cur_index == 2:
                        new_BGPRoute = self.rib[p][0]
                        if len(self.rib[p]) > 1:
                            new_backup_BGPRoute = self.rib[p][1]

                        yield previous_BGPRoute, new_BGPRoute, bgproute, previous_backup_BGPRoute, new_backup_BGPRoute

                cur_index += 1"""

    ###
    # @brief    This function computes all the prefix for peer that have an AS
    #           link in their AS path.
    #
    # @param    peer_ip     Peer IP address
    # @param    from_as     From AS of the AS Link we are focusing on
    # @param    to_as       To as of the AS Link we are focusing on
    #
    ###
    """
    NOT USED, NOT TESTED
    def get_arc_prefix(self, peer_ip, from_as, to_as):
        if peer_ip in self.rib_peer:
            for prefix, bgproute in self.rib_peer[peer_ip].items():
                last = None
                deep = 0
                for current in bgproute.as_path:
                    if last == from_as and current == to_as:
                        yield prefix, deep
                        break
                    last = current
                    deep += 1
    """

    ###
    # @brief    This function returns the bast backup peer IP address.
    #           The computation of the best backup is based on the size of the
    #           intersection of the AS path (which is different as the traditional
    #           comparaison).
    #
    # @param    peer_ip     IP address of the primary peer
    # @param    prefix      Prefix we are interested in
    #
    # @param    None if there is no backup router, otherwise the IP address of the
    #           best backup peer.
    ###
    """
    NOT USED, NOT TESTED
    def get_best_backup(self, peer_ip, prefix, opti=True):
        if opti:
            current_best = None
            if peer_ip in self.rib_peer and prefix in self.rib_peer[peer_ip]:
                inter_size = 0

                peer_as_set = set(self.rib_peer[peer_ip][prefix].as_path)
                peer_as_links_set = set()
                for i in range(0, len(self.rib_peer[peer_ip][prefix].as_path)-1):
                    peer_as_links_set.add((self.rib_peer[peer_ip][prefix].as_path[i], self.rib_peer[peer_ip][prefix].as_path[i+1]))

                print peer_as_links_set

                for p in self.rib[prefix]:
                    if p.peer_ip != peer_ip:

                        # Compute the set of links of the current as path
                        p_as_links_set = set()
                        for i in range(0, len(p.as_path)-1):
                            p_as_links_set.add((p.as_path[i], p.as_path[i+1]))
                        print p_as_links_set

                        if current_best is None:
                            current_best = p
                            inter_size = len(p_as_links_set.intersection(peer_as_links_set))
                            #inter_size = len(set(p.as_path).intersection(peer_as_set))
                            print inter_size, p
                        else:
                            #tmp_size = len(set(p.as_path).intersection(peer_as_set))
                            tmp_size = len(p_as_links_set.intersection(peer_as_links_set))
                            print tmp_size
                            if tmp_size < inter_size:
                                current_best = p
                                inter_size = tmp_size
                            print inter_size, p


            return None if current_best is None else current_best.peer_ip
        else:
            current_best = None
            if peer_ip in self.rib_peer and prefix in self.rib_peer[peer_ip]:
                for p in self.rib[prefix]:
                    if p.peer_ip != peer_ip:
                        if current_best is None:
                            current_best = p
                        else:
                            if len(current_best.as_path) > len(p.as_path):
                                current_best = p
            return None if current_best is None else current_best.peer_ip
    """

    ###
    # @brief    This function computes the backup route for a prefix which does
    #           not have an as link in its aspath. If all the as path of the backup
    #           have the link we would like to avoid, then this functions returns
    #           the backup with the shortest as-path.
    #
    # @param    peer_ip the peer IP address of the primary NH
    # @param    prefix  The prefix we are interested in
    # @param    aslink  The as link we want to avoid (if possible) (from_node, to_node)
    ###
    def get_backup_avoiding_aslink (self, peer_ip, prefix, as_link, traditional=False):
        selected_backup = None
        best_aspath_backup = None

        for bgproute in self.rib[prefix]:

            if bgproute.peer_ip != peer_ip:
                if best_aspath_backup is None:
                    best_aspath_backup = bgproute
                    if traditional:
                        break

                good_aspath = True

                for i in range(0, len(bgproute.as_path)-1):
                    if (bgproute.as_path[i], bgproute.as_path[i+1]) == as_link or \
                    (bgproute.as_path[i+1], bgproute.as_path[i]) == as_link:
                        good_aspath = False
                        break

                if good_aspath:
                    selected_backup = bgproute
                    break

        if selected_backup is None or traditional:
            return best_aspath_backup
        else:
            return selected_backup

    ###
    # @brief    This function tells if a peer is still a possible nexthop for a
    #           specific prefix.
    #
    # @param    prefix      The prefix we are looking for
    # @param    backup      The peer IP address
    #
    # @return   Boolean. True is the peer is a possible nexthop otherwise False.
    ###
    def backup_available(self, prefix, backup):
        if prefix in self.rib:
            for b in self.rib[prefix]:
                if b.peer_ip == backup:
                    return True
        return False

    def __str__(self):
        final_string = 'RIB\n'
        for prefix in self.rib:
            final_string += str(prefix)+'\n'
            for bgproute in self.rib[prefix]:
                final_string += '\t'+str(bgproute)+'\n'

        final_string += 'RIB PEER\n'
        for peer in self.rib_peer:
            final_string += str(peer)+'\n'
            for prefix in self.rib_peer[peer]:
                final_string += '\t'+prefix+'\t'+str(self.rib_peer[peer][prefix].as_path)+'\n'

        return final_string.rstrip()

    def print_size(self):
        final_string = "RIB total size: "+str(len(self.rib))+"\n"

        for peer_ip in self.rib_peer:
            final_string += str(peer_ip)+'\t'+str(len(self.rib_peer[peer_ip]))+'\n'

        return final_string

    def print_prefix_rib(self, prefix):
        final_string = 'RIB for '+prefix+'\n'
        for bgproute in self.rib[prefix]:
            final_string += '\t'+str(bgproute)+'\n'

        return final_string




if __name__ == '__main__':

    rib = RIBGlobal()

    def init_rib():

        aspath1 = [12, 13, 14]
        bgproute1 = BGPRoute('1.0.0.0/24', '1.1.1.1', aspath1, None)
        aspath2 = [12, 13, 14, 15]
        bgproute2 = BGPRoute('1.0.0.0/24', '1.1.1.1', aspath2, None)
        aspath3 = [12, 20, 15, 14]
        bgproute3 = BGPRoute('1.0.0.0/24', '2.1.1.1', aspath3, None)
        aspath4 = [12, 13, 34, 14, 15, 67, 6]
        bgproute4 = BGPRoute('1.0.0.0/24', '3.1.1.1', aspath4, None)
        aspath5 = [12, 13, 12, 15, 14]
        bgproute5 = BGPRoute('1.0.0.0/24', '3.1.1.1', aspath5, None)
        aspath6 = [49, 13, 34, 45, 56, 15687, 6, 16, 14]
        bgproute6 = BGPRoute('1.0.0.0/24', '3.1.1.1', aspath6, None)

        old_route,new_route,old_route_peer, old_backup, new_backup = rib.announce(bgproute1)
        old_route,new_route,old_route_peer, old_backup, new_backup = rib.announce(bgproute2)
        old_route,new_route,old_route_peer, old_backup, new_backup = rib.announce(bgproute3)
        old_route,new_route,old_route_peer, old_backup, new_backup = rib.announce(bgproute4)
        old_route,new_route,old_route_peer, old_backup, new_backup = rib.announce(bgproute5)
        old_route,new_route,old_route_peer, old_backup, new_backup = rib.announce(bgproute6)

    init_rib()

    print rib
    print '-----------'
    #print rib.get_best_backup('1.1.1.1', '1.0.0.0/24')
    print rib.get_backup_avoiding_aslink('1.1.1.1', '1.0.0.0/24', (15,14))
    print rib.get_backup_avoiding_aslink('1.1.1.1', '1.0.0.0/24', (15,14), traditional=True)

    #print old
    #print new
    #print old_peer
    """print str(rib)
    print (str(objgraph.show_most_common_types(limit=40)))
    print (str(objgraph.show_growth()))
    def clean():
        old,new, old_peer = rib.withdraw('3.1.1.1', '1.0.0.0/24')
        old,new,old_peer = rib.withdraw('2.1.1.1', '1.0.0.0/24')
        old,new,old_peer = rib.withdraw('3.1.1.1', '1.0.0.0/24')
        old,new,old_peer = rib.withdraw('1.1.1.1', '1.0.0.0/24')
        print str(rib)
    clean()
    print (str(objgraph.show_most_common_types(limit=40)))
    print (str(objgraph.show_growth()))
    print '----------'"""
