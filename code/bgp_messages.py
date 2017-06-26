import argparse
from collections import deque


class BGPMessage:
    def __init__(self, mtype, peer_id, peer_as, time, prefix, as_path=None, description=None):
        self.mtype = mtype
        self.peer_id = peer_id
        self.peer_as = peer_as
        self.time = time
        self.prefix = prefix
        self.as_path = as_path
        self.description = description

    def __str__(self):
        if self.prefix is not None:
            res = str(self.description)+'|'+self.mtype+'|'+self.peer_id+'|'+str(self.peer_as)+'|'+str(self.time)+'|'+self.prefix+'|'+str(self.as_path)
        else:
            res = str(self.description)+'|'+self.mtype+'|'+self.peer_id+'|'+str(self.peer_as)+'|'+str(self.time)+'|'+str(self.as_path)
        return res

class BGPMessagesQueue(deque):
    def __init__(self, time):
        super(BGPMessagesQueue, self).__init__()
        self.time = time

    """
    Remove all the bgp messages in the queue that have expired
    """
    def refresh(self, ts):
        while len(self) > 0 and ts - self[0].time > self.time:
            self.popleft()

    """
    Remove all the bgp messages in the queue that have expired.
    And yields the expired messages.
    """
    def refresh_iter(self, ts):
        while len(self) > 0 and ts - self[0].time > self.time:
            yield self.popleft()

"""
Parse a bgp message from bgpdump or CBGP.
Return a BGP message object.
"""
def parse(msg):
    if len(msg) > 0 and msg[0] is not '#':
        linetab = msg.rstrip('\n').split('|')
        if linetab[1] == 'BGP4': # c-bgp
            if linetab[3] == 'A':
                try:
                    as_path = clean_aspath(map(lambda x: int(x), linetab[7].split(' ')))
                except:
                    print 'ERROR: '+str(msg)
                return BGPMessage(linetab[3], linetab[0]+'-'+linetab[4], as_path[0], float(linetab[2]), linetab[6], as_path, 'CBGP')
            elif linetab[3] == 'W':
                return BGPMessage(linetab[3], linetab[0]+'-'+linetab[4], None, float(linetab[2]), linetab[6], None, 'CBGP')
            elif linetab[3] == 'CLOSE':
                return BGPMessage(linetab[3], linetab[0]+'-'+linetab[4], None, float(linetab[2]), None, None, 'CBGP')
            elif linetab[3] == 'INFO':
                return BGPMessage(linetab[3], linetab[0]+'-'+linetab[4], None, float(linetab[2]), linetab[6]+'_'+linetab[7], None, 'CBGP')
            else:
                return None

        elif linetab[0] == 'BGP4MP': # RIPE's updates
            if linetab[2] == 'A':
                as_path = clean_aspath(map(lambda x: int(x), linetab[6].split(' ')))
                return BGPMessage(linetab[2], linetab[3], int(linetab[4]), float(linetab[1]), linetab[5], as_path, 'BGP4MP')
            elif linetab[2] == 'W':
                return BGPMessage(linetab[2], linetab[3], int(linetab[4]), float(linetab[1]), linetab[5], None, 'BGP4MP')
            elif linetab[2] == 'CLOSE':
                return BGPMessage(linetab[2], linetab[3], int(linetab[4]), float(linetab[1]), None, None, 'BGP4MP')
            else:
                return None

        elif linetab[0] == 'TABLE_DUMP2':
            if linetab[2] == 'B':
                try:
                    as_path = clean_aspath(map(lambda x: int(x), linetab[6].split(' ')))
                except ValueError:
                    as_path = []
                return BGPMessage('A', linetab[3], int(linetab[4]), float(linetab[1]), linetab[5], as_path, 'TABLE_DUMP2')

        elif linetab[0] == 'BGPSTREAM':
            if linetab[2] == 'A' or linetab[2] == 'R':
                as_path = clean_aspath(map(lambda x: int(x), linetab[7].split(' ')))
                return BGPMessage('A', linetab[1]+'-'+linetab[3], int(linetab[4]), float(linetab[5]), linetab[6], as_path, 'BGPSTREAM')
            elif linetab[2] == 'W':
                return BGPMessage(linetab[2], linetab[1]+'-'+linetab[3], int(linetab[4]), float(linetab[5]), linetab[6], None, 'BGPSTREAM')
            elif linetab[2] == 'CLOSE':
                return BGPMessage(linetab[2], linetab[1]+'-'+linetab[3], int(linetab[4]), float(linetab[5]), None, None, 'BGPSTREAM')


"""
Remove duplicate ASes in case of AS-path prepending.
Check for loops in the as-path.
Return the non-duplicated AS-path or None if there was a loop.
"""
def clean_aspath(as_path):
    prev = None
    as_set = set()
    final_as_path = []

    for asn in as_path:
        if asn != prev:
            if asn in as_set:
                return []
            else:
                as_set.add(asn)
                final_as_path.append(asn)
        prev = asn
    return final_as_path

if __name__ == '__main__':

    parser = argparse.ArgumentParser("This script parses bgp messages.")
    parser.add_argument("infile", type=str, help="Infile")
    args = parser.parse_args()
    infile = args.infile

    with open(infile, 'r') as fd:
        for line in fd.readlines():
            bgp_msg = parse(line)
            print bgp_msg

    print clean_aspath([1,2,3,3,3,4,4,4,4,5])
