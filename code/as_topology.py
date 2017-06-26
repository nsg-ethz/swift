import networkx as nx
import math

class ASTopology(nx.DiGraph):
    def __init__(self, w_threshold, silent=False):
        super(ASTopology, self).__init__()
        self.silent = silent
        self.nodes_forward = set() # Set of nodes that needs to be taken into account when looking for the best fm score
        self.nodes_backward = set() # Set of nodes that needs to be taken into account when looking for the best fm score
        self.w_threshold = w_threshold

    def add(self, as_path, prefix=None):
        for i in range(0, len(as_path)-1):
            # Create the node and initialize their attributes if they do not exist yet
            if as_path[i] not in self:
                self.add_node(as_path[i], out_prefixes=0, in_prefixes=0)
            if as_path[i+1] not in self:
                self.add_node(as_path[i+1], out_prefixes=0, in_prefixes=0)

            # Update the node attributes
            self.node[as_path[i]]['out_prefixes'] += 1
            self.node[as_path[i+1]]['in_prefixes'] += 1

            # Add those nodes in the out_prefixes our in_prefixes sets if necessary
            if self.node[as_path[i]]['out_prefixes'] == self.w_threshold:
                self.nodes_forward.add(as_path[i])
            if self.node[as_path[i+1]]['in_prefixes'] == self.w_threshold:
                self.nodes_backward.add(as_path[i+1])

            # Create the edge
            self.add_edge(as_path[i], as_path[i+1])

            # Update the prefix counter
            if 'prefix_counter' not in self[as_path[i]][as_path[i+1]]:
                self[as_path[i]][as_path[i+1]]['prefix_counter'] = 0.
            self[as_path[i]][as_path[i+1]]['prefix_counter'] += 1.

            # Update the depth prefix counter
            if 'depth' not in self[as_path[i]][as_path[i+1]]:
                self[as_path[i]][as_path[i+1]]['depth'] = {}
            if i+1 not in self[as_path[i]][as_path[i+1]]['depth']:
                self[as_path[i]][as_path[i+1]]['depth'][i+1] = 0
            self[as_path[i]][as_path[i+1]]['depth'][i+1] += 1

            # Update the prefix set (if not silent only)
            if not self.silent and prefix is not None:
                if 'prefixes' not in self[as_path[i]][as_path[i+1]]:
                    self[as_path[i]][as_path[i+1]]['prefixes'] = set()
                self[as_path[i]][as_path[i+1]]['prefixes'].add(prefix)

    def remove(self, as_path, prefix=None):
        for i in range(0, len(as_path)-1):
            # Update the node attributes
            self.node[as_path[i]]['out_prefixes'] -= 1
            self.node[as_path[i+1]]['in_prefixes'] -= 1

            # Add those nodes in the out_prefixes our in_prefixes sets if necessary
            if self.node[as_path[i]]['out_prefixes'] == self.w_threshold-1:
                self.nodes_forward.remove(as_path[i])
            if self.node[as_path[i+1]]['in_prefixes'] == self.w_threshold-1:
                self.nodes_backward.remove(as_path[i+1])

            # Update the weight
            self[as_path[i]][as_path[i+1]]['prefix_counter'] -= 1.

            # Update the depth prefix counter
            self[as_path[i]][as_path[i+1]]['depth'][i+1] -= 1
            if self[as_path[i]][as_path[i+1]]['depth'][i+1] == 0:
                del self[as_path[i]][as_path[i+1]]['depth'][i+1]

            # Update the prefix set (if not silent only)
            if not self.silent and prefix is not None:
                self[as_path[i]][as_path[i+1]]['prefixes'].remove(prefix)

            # Clean the graph
            if self[as_path[i]][as_path[i+1]]['prefix_counter'] == 0.:
                self.remove_edge(as_path[i], as_path[i+1])
                if self.out_degree(as_path[i]) == 0 and self.in_degree(as_path[i]) == 0.:
                    self.remove_node(as_path[i])
                if self.out_degree(as_path[i+1]) == 0 and self.in_degree(as_path[i+1]) == 0.:
                    self.remove_node(as_path[i+1])


    def print_nodes(self):
        list_nodes = []
        for n in self.nodes():
            list_nodes.append((n, self.node[n]['out_prefixes'], self.node[n]['in_prefixes']))

        list_nodes = sorted(list_nodes, reverse=True, key=lambda x:x[1])

        res = ''
        for i in list_nodes:
            res += str(i[0])+'\t'+str(i[1])+'\t'+str(i[2])+'\n'

        print self.nodes_forward
        print self.nodes_backward

        return res

    def get_prefixes_edge(self, edge):
        try:
            for p in self[edge[0]][edge[1]]['prefixes']:
                yield p
        except KeyError:
            return

    def __str__(self):
        res = ''
        for i in self:
            for j in self[i]:
                res += str(i)+'\t'+str(j)+'\t'+str(self[i][j]['prefix_counter'])+'\n'
        return res

    def get_depth(self, from_node, to_node):
        depth = '-1'
        if from_node in self and to_node in self[from_node]:
            depth = min(self[from_node][to_node]['depth'].keys())

        return depth

    """
    Return a string with the description of the topology. Only the edges with the
    the top _limit_ weight are shown.
    """
    def print_subtopo(self, limit=10):
        list_edges = []
        for i in self:
            for j in self[i]:
                list_edges.append((i, j, self[i][j]['prefix_counter']))

        list_edges_sorted = sorted(list_edges, reverse=True, key=lambda x:x[2])

        res = ''
        for i in range(0, min(len(list_edges_sorted),limit)):
            res += str(list_edges_sorted[i][0])+'\t'+str(list_edges_sorted[i][1])+'\t'+str(list_edges_sorted[i][2])+'\t'+str(self[list_edges_sorted[i][0]][list_edges_sorted[i][1]]['depth'])+'\n'
        return res

    import math


    def fowlkes_mallows(self, TP, FP, FN, w_p=1., w_r=1.):
        return math.exp((w_p*math.log(TP/(TP+FP)) + w_r*math.log(TP/(TP+FN))) / (w_p+w_r))

    def draw_graph(self, peer_as, G, current_burst, outfile='as_graph.dot', threshold=100):

        res = 'digraph G {\n'+str(peer_as)+' [color=red];\n'

        all_prefixes = float(len(current_burst.real_prefixes))+1500

        for e in self.edges():
            if self[e[0]][e[1]]['prefix_counter'] > threshold:
                gw_counter = float(self[e[0]][e[1]]['prefix_counter'])
                try:
                    g_counter = float(G[e[0]][e[1]]['prefix_counter'])
                except:
                    g_counter = 0
                g_counter += gw_counter

                fm_score = "%.2f" % self.fowlkes_mallows(gw_counter, g_counter, all_prefixes-gw_counter, w_r=3.)
                res += str(e[0])+' -> '+str(e[1])+' [label="'+str(int(gw_counter))+'/'+str(int(g_counter))+' ('+str(fm_score)+')"];\n'

        res += '}'

        fd = open(outfile, 'w')
        fd.write(res)
        fd.close()
