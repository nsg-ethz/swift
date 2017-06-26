import socket
import argparse

parser = argparse.ArgumentParser("This script connects to a server and sends bgp messages read from a file.")
parser.add_argument("dst_ip", type=str, help="Server IP")
parser.add_argument("port", type=int, help="Port")
parser.add_argument("infile", type=str, help="Infile")
args = parser.parse_args()
dst = args.dst_ip
port = args.port
infile = args.infile

socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
socket.connect((dst, port))
print 'Connected to ',dst,' port ',port

with open(infile, 'r') as fd:
    for line in fd.readlines():
        if line[0] != '#':
            #print line
            linetab = line.split('|')
            linetab[2] = '10000'
            line = '|'.join(linetab)

            socket.send(line)

socket.close()
