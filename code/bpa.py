import math
import time
from as_topology import ASTopology

"""
Compute the Fowlkes Mallows score based on the True-Positive, False-Positive and False-Negative.
The precision and the recall can be weighted.
Pseudo-code:

fowlkes_mallows (TP, FP, FN, w_p=1, w_r=1):
    return math.exp((w_p*math.log(TP/(TP+FP)) + w_r*math.log(TP/(TP+FN))) / (w_p+w_r))

"""
def fowlkes_mallows(TP, FP, FN, w_p=1., w_r=1.):
    return math.exp((w_p*math.log(TP/(TP+FP)) + w_r*math.log(TP/(TP+FN))) / (w_p+w_r))

def find_best_fmscore_naive(G, G_W, W_nb, from_node, p_w, r_w):
    # Compute a list of outgoing edges with their TP, FP and FN values
    ngh_fm = []

    current_TP = 0
    current_FP = 0
    current_FN = 0
    current_set = set()
    current_fmscore = 0

    from_node_set = set()
    if from_node in G:
        from_node_set = from_node_set.union(G[from_node].keys())
    if from_node in G_W:
        from_node_set = from_node_set.union(G_W[from_node].keys())

    for to_node in from_node_set:
        current_set.add((from_node, to_node))
        try:
            current_TP += G_W[from_node][to_node]['prefix_counter']
        except: pass
        try:
            current_FP += G[from_node][to_node]['prefix_counter']
        except: pass

    current_FN = W_nb - current_TP # Should be equal to 0
    if current_TP == 0:
        current_fmscore = 0
    else:
        current_fmscore = fowlkes_mallows(current_TP, current_FP, current_FN, p_w, r_w)

    return current_set, current_fmscore, current_TP, current_FP, current_FN

def find_best_fmscore_single(G, G_W, W_nb, p_w=1, r_w=1):

    best_fm_score = 0
    best_edge_set = set()
    best_TP = 0
    best_FP = 0
    best_FN = 0

    for from_node in G_W.nodes_forward:
        # Compute a list of outgoing edges with their TP, FP and FN values
        current_fmscore = 0

        for to_node in G_W[from_node].keys():
            TP = G_W[from_node][to_node]['prefix_counter']
            try:
                FP = G[from_node][to_node]['prefix_counter']
            except:
                FP = 0
            FN = W_nb - TP

            if TP > 0:
                current_fmscore = fowlkes_mallows(TP, FP, FN, p_w, r_w)

            # Update the best FM score if the current FM score is better
            if best_fm_score < current_fmscore:
                best_edge_set = set()
                best_edge_set.add((from_node, to_node))
                best_fm_score = current_fmscore
                best_TP = TP
                best_FP = FP
                best_FN = FN
            #elif best_fm_score == current_fmscore:
            #    best_edge_set.add((from_node, to_node))

    return best_edge_set, best_fm_score, best_TP, best_FP, best_FN

"""
This function finds the set of AS links with the highest Fowlkes-Mallows score.
The links in the output set have a common source node (forward).
There is a similar function which computes this in a backward fashion, i.e. returns the
set of links with the highest FM score, and which have the same
destination node.
"""
def find_best_fmscore_forward(G, G_W, W_nb, p_w=1, r_w=1, opti=True):

    best_fm_score = 0
    best_edge_set = set()
    best_TP = 0
    best_FP = 0
    best_FN = 0

    for from_node in G_W.nodes_forward:
        # Compute a list of outgoing edges with their TP, FP and FN values
        ngh_fm = []

        for to_node in G_W[from_node].keys():

            TP = G_W[from_node][to_node]['prefix_counter']
            try:
                FP = G[from_node][to_node]['prefix_counter']
            except:
                FP = 0
            FN = W_nb - TP

            if TP > 0:
                ngh_fm.append((to_node, TP, FP, FN, fowlkes_mallows(TP, FP, FN, p_w, r_w)))

        # Sort the list based on the Fowlkes Mallows metric
        ngh_fm_sorted = sorted(ngh_fm, key=lambda x : x[4], reverse=True)

        # Find the set of edges with the highest FM score using the Greedy algorithm
        current_set = set()
        current_TP = 0
        current_FP = 0
        current_FN = 0
        current_fmscore = 0

        while len(ngh_fm_sorted) > 0:
            new_ngh = ngh_fm_sorted.pop(0)

            new_TP = current_TP + new_ngh[1]
            new_FP = current_FP + new_ngh[2]
            new_FN = W_nb - new_TP

            if fowlkes_mallows(new_TP, new_FP, new_FN, p_w, r_w) > current_fmscore:
                current_set.add((from_node, new_ngh[0]))
                current_TP = new_TP
                current_FP = new_FP
                current_FN = new_FN
                current_fmscore = fowlkes_mallows(current_TP, current_FP, current_FN, p_w, r_w)
            elif opti:
                break # Greedy algorithm

        # Update the best FM score if the current FM score is better
        if best_fm_score < current_fmscore:
            best_edge_set = current_set
            best_fm_score = current_fmscore
            best_TP = current_TP
            best_FP = current_FP
            best_FN = current_FN
        elif best_fm_score == current_fmscore:
            best_edge_set = best_edge_set.union(current_set)
            best_TP = -1
            best_FP = -1
            best_FN = -1

    return best_edge_set, best_fm_score, best_TP, best_FP, best_FN

"""
This function finds the set of AS edges with the highest Fowlkes-Mallows score.
Each set of edges considered here have a common destination node (backward).
The links need to have an AS in common (where the failure occured).
For the moment, we only focus on withdraws.
"""
def find_best_fmscore_backward(G, G_W, W_nb, p_w=1, r_w=1, opti=True):

    best_fm_score = 0
    best_edge_set = set()
    best_TP = 0
    best_FP = 0
    best_FN = 0

    for to_node in G_W.nodes_backward:
        # Compute a list of incoming edges with their TP, FP and FN values
        ngh_fm = []

        for from_node in G_W.predecessors(to_node):
            TP = G_W[from_node][to_node]['prefix_counter']
            try:
                FP = G[from_node][to_node]['prefix_counter']
            except:
                FP = 0
            FN = W_nb - TP

            ngh_fm.append((from_node, TP, FP, FN, fowlkes_mallows(TP, FP, FN, p_w, r_w))) # ngh_fm is a list of 4-tuples (node id, TP, FP, FN, FMscore)

        # Sort the list based on the Fowlkes Mallows metric
        ngh_fm_sorted = sorted(ngh_fm, key=lambda x : x[4], reverse=True)        #print ngh_fm_sorted

        # Find the set of edges with the highest FM score using the Greedy algorithm
        current_set = set()
        current_TP = 0
        current_FP = 0
        current_FN = 0
        current_fmscore = 0

        while len(ngh_fm_sorted) > 0:
            new_ngh = ngh_fm_sorted.pop(0)

            new_TP = current_TP + new_ngh[1]
            new_FP = current_FP + new_ngh[2]
            new_FN = W_nb - new_TP

            if fowlkes_mallows(new_TP, new_FP, new_FN, p_w, r_w) > current_fmscore:
                current_set.add((new_ngh[0], to_node))
                current_TP = new_TP
                current_FP = new_FP
                current_FN = new_FN
                current_fmscore = fowlkes_mallows(current_TP, current_FP, current_FN, p_w, r_w)
            elif opti:
                break # Greedy algorithm

        # Update the best FM score if the current FM score is better
        if best_fm_score < current_fmscore:
            best_edge_set = current_set
            best_fm_score = current_fmscore
            best_TP = current_TP
            best_FP = current_FP
            best_FN = current_FN
        elif best_fm_score == current_fmscore:
            best_edge_set = best_edge_set.union(current_set)
            best_TP = -1
            best_FP = -1
            best_FN = -1

    return best_edge_set, best_fm_score, best_TP, best_FP, best_FN


if __name__ == '__main__':
    import networkx as nx
    from random import randint
    import pickle

    """G = pickle.load(open('G.pickled', 'r'))
    G_W = pickle.load(open('G.pickled', 'r'))

    print 'Loaded!'

    W_queue = range(0, 40000)

    best_edge_set, best_fm_score = find_best_fmscore_forward(G, None, G_W, None, W_queue)
    print best_edge_set
    print best_fm_score"""


    TP = 2252. # hit
    FP = 0 # predicted
    FN = 17072.-2252. # missed

    precision = TP/(TP+FP)
    recall = TP/(TP+FN)

    print precision
    print recall
    print fowlkes_mallows(TP, FP, FN, 1, 3)

    print '---'


    TP = 3747. # hit
    FP = 258547.-3747. # predicted
    FN = 17072.-3747. # missed

    precision = TP/(TP+FP)
    recall = TP/(TP+FN)

    print precision
    print recall
    print fowlkes_mallows(TP, FP, FN, 1, 3)

    print '---'

    TP = 3747+2252. # hit
    FP = 258547.-3747. # predicted
    FN = 17072.-3747.-2252. # missed

    precision = TP/(TP+FP)
    recall = TP/(TP+FN)

    print precision
    print recall
    print fowlkes_mallows(TP, FP, FN, 1, 3)

    print '---'

    TP = 1070. # hit
    FP = 1813.-1070. # predicted
    FN = 17072.-1070. # missed

    precision = TP/(TP+FP)
    recall = TP/(TP+FN)

    print precision
    print recall
    print fowlkes_mallows(TP, FP, FN, 1, 3)
    """G = nx.DiGraph()
    G_W = nx.DiGraph()

    edges_list = [(1,2),(1,3),(2,5),(2,6),(3,4),(5,7),(5,8),(5,9),(5,10),(7,11),(7,12),(8,13),(8,14),(10,15)]
    G.add_edges_from(edges_list)
    edges_list = [(1,2),(1,3),(2,5),(2,6),(3,4),(5,7),(5,8),(5,9),(5,10),(7,11),(8,13),(8,14),(10,15)]
    G_W.add_edges_from(edges_list)

    G[1][2]['prefix_counter'] = 400.
    G[2][5]['prefix_counter'] = 301.
    G[1][3]['prefix_counter'] = 495.
    G[2][6]['prefix_counter'] = 99.
    G[3][4]['prefix_counter'] = 296.
    G[5][7]['prefix_counter'] = 85.
    G[5][8]['prefix_counter'] = 88.
    G[5][9]['prefix_counter'] = 87.
    G[5][10]['prefix_counter'] = 99.
    G[7][11]['prefix_counter'] = 83.
    G[7][12]['prefix_counter'] = 10.
    G[8][13]['prefix_counter'] = 40.
    G[8][14]['prefix_counter'] = 49.
    G[10][15]['prefix_counter'] = 99.

    G_W[1][2]['prefix_counter'] = 100.
    G_W[2][5]['prefix_counter'] = 99.
    G_W[1][3]['prefix_counter'] = 5.
    G_W[2][6]['prefix_counter'] = 1.
    G_W[3][4]['prefix_counter'] = 4.
    G_W[5][7]['prefix_counter'] = 50.
    G_W[5][8]['prefix_counter'] = 22.
    G_W[5][9]['prefix_counter'] = 26.
    G_W[5][10]['prefix_counter'] = 1.
    G_W[7][11]['prefix_counter'] = 50.
    G_W[8][13]['prefix_counter'] = 20.
    G_W[8][14]['prefix_counter'] = 2.
    G_W[10][15]['prefix_counter'] = 1.

    tmp_list = range(0, 105)

    best_edge_set, best_fm_score = find_best_fmscore_forward(G, None, G_W, None, tmp_list)
    print best_edge_set
    print best_fm_score

    best_edge_set, best_fm_score = find_best_fmscore_backward(G, None, G_W, None, tmp_list)
    print best_edge_set
    print best_fm_score"""

    """edges_list = [(1,2),(1,3),(1,4),(2,5),(2,6),(3,5),(3,6),(4,5),(4,6),(5,7),(6,7)]
    G.add_edges_from(edges_list)
    edges_list = [(1,2),(1,3),(1,4),(2,5),(2,6),(3,6),(4,6),(6,7)]
    G_W.add_edges_from(edges_list)

    G[1][2]['prefix_counter'] = 85.
    G[1][3]['prefix_counter'] = 87.
    G[1][4]['prefix_counter'] = 99.
    G[2][5]['prefix_counter'] = 49.
    G[2][6]['prefix_counter'] = 36.
    G[3][5]['prefix_counter'] = 50.
    G[3][6]['prefix_counter'] = 37.
    G[4][5]['prefix_counter'] = 50.
    G[4][6]['prefix_counter'] = 49.
    G[5][7]['prefix_counter'] = 150.
    G[6][7]['prefix_counter'] = 93.

    G_W[1][2]['prefix_counter'] = 15.
    G_W[1][3]['prefix_counter'] = 13.
    G_W[1][4]['prefix_counter'] = 1.
    G_W[2][5]['prefix_counter'] = 1.
    G_W[2][6]['prefix_counter'] = 14.
    G_W[3][6]['prefix_counter'] = 13.
    G_W[4][6]['prefix_counter'] = 1.
    G_W[6][7]['prefix_counter'] = 7.

    tmp_list = range(0, 29)

    best_edge_set, best_fm_score = find_best_fmscore_forward(G, None, G_W, None, tmp_list)
    print best_edge_set
    print best_fm_score

    best_edge_set, best_fm_score = find_best_fmscore_backward(G, None, G_W, None, tmp_list)
    print best_edge_set
    print best_fm_score"""

    """#Dtmp=nx.gn_graph(1000, kernel=lambda x:x**3)    # the GN graph
    Gtmp=G=nx.scale_free_graph(5000)
    print len(Gtmp.edges())

    G = nx.DiGraph()
    G.add_edges_from(Gtmp.edges())
    DG = G.copy()
    #print G.nodes()

    for e in G.edges():
        G[e[0]][e[1]]['prefix_counter'] = float(randint(0, 1000))
    print G

    G_W = G.copy()
    for e in G_W.edges():
        G_W[e[0]][e[1]]['prefix_counter'] = float(randint(0, G[e[0]][e[1]]['prefix_counter']))

    tmp_list = range(0, 1500)

    for i in G:
        for j in G[i]:
            print str(i)+' '+str(j)+' '+str(G[i][j]['prefix_counter'])+'\t'+str(i)+' '+str(j)+' '+str(G_W[i][j]['prefix_counter'])

    best_edge_set, best_fm_score = find_best_fmscore_forward(G, None, G_W, None, tmp_list)
    print best_edge_set
    print best_fm_score

    best_edge_set, best_fm_score = find_best_fmscore_backward(G, None, G_W, None, tmp_list)
    print best_edge_set
    print best_fm_score"""
