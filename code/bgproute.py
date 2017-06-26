class BGPRoute:
    def __init__(self, prefix, peer_ip, as_path, partial_vmac=''):
        self.prefix = prefix
        self.peer_ip = peer_ip
        self.as_path = as_path
        self.partial_vmac = partial_vmac

    def __cmp__(self, other):
        if other is None:
            return -1

        #Positive and negative reversed since this is being used for a max pq, not a minpq
        if(len(self.as_path) < len(other.as_path)):
            return -1
        if(len(self.as_path) > len(other.as_path)):
            return 1

        #If two AS share the same path length, compare based on peer IP address
        elif(self.peer_ip < other.peer_ip):
            return -1
        elif(self.peer_ip > other.peer_ip):
            return 1

        # Two BGPRoutes with two different AS path but with the same length
        # are NOT equal
        if self.peer_ip < other.peer_ip:
            return -1
        elif self.peer_ip > other.peer_ip:
            return 1

        for i, j in zip(self.as_path, other.as_path):
            if i > j:
                return -1
            if i < j:
                return 1

        return 0

    def __str__(self):
        return str(self.peer_ip)+'\t'+str(self.prefix)+'\t'+str(self.as_path)+'\t'+str(self.partial_vmac)
