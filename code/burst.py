
class Burst:

    def __init__(self, peer_id, start_time, duration, outdir, encoding, W_queue, silent=False):
        self.peer_id = peer_id
        self.start_time = int(start_time)
        self.duration = duration
        self.outdir = outdir
        self.silent = silent
        self.encoding = encoding
        self.last_ts = start_time

        # Variable to keep the number of withdrawals removed from the queue during the burst
        self.deleted_from_W_queue = []

        # Set with the predicted prefixes
        self.predicted_prefixes = set()
        # Set with the real prefixes
        self.real_prefixes = set()

        # Set with the failed AS-edges
        self.as_edges = set()

        # Boolean. True if the a prediction has been done for that burst, otherwise False
        self.prediction_done = False

        # Info file
        self.info_file = outdir+'/bursts_info'

        self.ts_100th_w = W_queue[100].time if len(W_queue) > 100 else W_queue[0].time

        # Open the file for the real prefixes of this burst
        self.fd_real = open(outdir+'/'+str(self.peer_id)+'_'+str(self.start_time)+'_real', 'w', 1)
        self.fd_predicted = open(outdir+'/'+str(self.peer_id)+'_'+str(self.start_time)+'_predicted', 'w', 1)
        self.fd_predicted.write('# Started burst!\n#100thTS\t'+str(self.ts_100th_w)+'\n')
        self.fd_real.write('# Started burst!\n#100thTS\t'+str(self.ts_100th_w)+'\n')

        # Write the prefixes currently in the queue in the real set of prefixes
        # (but  not added in real set of prefixes)
        for p in W_queue:
            self.fd_real.write(p.prefix+'|'+str(p.time)+'|B|'+str(' '.join(map(lambda x:str(x), p.as_path)))+'\n')

    """
    Stop the burst when it expires. This essentially means close the file descriptors.
    """
    def stop(self, stop_time):
        self.fd_real.close()
        self.fd_predicted.close()

        with open(self.info_file, 'a') as fd:
            fd.write(self.peer_id+'\t'+str(self.start_time)+'\t'+str(self.last_ts)+'\t'+str(self.duration)+'\t'+str(len(self.real_prefixes))+'\t'+str(self.ts_100th_w)+'\n')

    """
    Check if the burst is expired
    """
    def is_expired(self, time):
        return not time-self.start_time <= self.duration

    """
    Add a real prefix to this burst
    """
    def add_real_prefix(self, time, prefix, mtype, old_as_path):
        if not self.silent:
            tag = 'B' # Used to indicate if this prefixe arrived before or after the prediction
            if self.prediction_done:
                tag = 'A'

            if mtype == 'W':
                if prefix not in self.real_prefixes:
                    self.fd_real.write(prefix+'|'+str(int(time))+'|W|'+str(tag)+'|'+str(' '.join(map(lambda x:str(x), old_as_path)))+'\n')

            elif mtype == 'A':
                self.fd_real.write(prefix+'|'+str(int(time))+'|A|'+str(tag)+'|'+str(' '.join(map(lambda x:str(x), old_as_path)))+'\n')

        # Add the prefix in real set of withdrawn prefixes
        if mtype == 'W':
            self.real_prefixes.add(prefix)

    """
    Add a predicted prefix in the predicted set of prefix of this burst.
    """
    def add_predicted_prefix(self, time, prefix, encoded, depth):
        if not self.silent:
            if prefix not in self.predicted_prefixes:
                if encoded:
                    self.predicted_prefixes.add(prefix)
                    self.fd_predicted.write('PREFIX|'+prefix+'|'+str(int(time))+'|'+str(len(self))+'|'+'Y|'+str(depth)+'\n')

                else:
                    self.fd_predicted.write('PREFIX|'+prefix+'|'+str(int(time))+'|'+str(len(self))+'|'+'N|'+str(depth)+'\n')

    """
    Add a predicted prefix in the predicted set of prefix of this burst.
    """
    def add_predicted_prefix2(self, time, prefix, encoded, depth):
        self.fd_predicted.write('PREFIX|'+prefix+'|'+str(int(time))+'|'+str(len(self))+'|'+'?|'+str(depth)+'\n')

    """
    Add a set of edges to the set of edges of the burst.
    Returns the edges that were not added yet.
    G_W is needed to compute how far is the link from the SWIFT router
    """
    def add_edges_iter(self, time, edges_set, G_W):
        for edge in edges_set:
            if edge not in self.as_edges:
                # Compute how far the edge is from the SWIFT router
                depth = G_W.get_depth(edge[0], edge[1])

                self.as_edges.add(edge)
                if not self.silent:
                    self.fd_predicted.write('EDGE|'+str(edge[0])+','+str(edge[1])+'|'+str(int(time))+'|'+str(len(self))+'|'+str(depth)+'\n')
                yield edge

    """
    Return the number of uniq withdrawals in this burst.
    """
    def __len__(self):
        return len(self.real_prefixes)
