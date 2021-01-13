from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_0
from ryu.lib.mac import haddr_to_bin
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.topology import event
from ryu.topology.api import get_switch, get_link,get_all_link
from ryu.lib.packet import ethernet, ipv6
from ryu.app.ofctl.api import get_datapath
import pickle, os, time

switchTopo = {}
hostTopo = {}
paths = {}

def dijkstra(src, x, dest, visited, distances, predecessors):
    """
    This function does the dijkstra algorithm and finds the shortest path between two hosts
    """
    global switchTopo
    if x == dest:
        #If the path is found, we iterate them from last to first by predecessors to find path
        path = []
        temp = dest
        while(temp != src):
            path.append(temp)
            temp = predecessors[temp]
        path.append(src)
        return "-".join(path[::-1]), "-".join(path)
    else:
        #Going through neibors of selected node and updating their distances
        for neighbor in switchTopo[x]:
            if neighbor not in visited:
                new_distance = distances[x] + switchTopo[x][neighbor]
                if new_distance < distances[neighbor]:
                    distances[neighbor] = new_distance
                    predecessors[neighbor] = x

        visited.append(x)
        minimum = float("inf")
        #Finding the next minimum distance node
        minimumNode = None
        for k in switchTopo:
            if((k not in visited) and (distances[k] < minimum)):
                minimum = distances[k]
                minimumNode = k
        #Calling this function recursively
        return dijkstra(src, minimumNode, dest, visited, distances, predecessors)


def read_information(file_name: str, hosts: list, switches: list, links: list):
    with open(file_name, 'r') as f:
        lines = f.readlines()
        switches_number = int(lines[0].replace('\n', ''))
        hosts_number = int(lines[1].replace('\n', ''))
        for i in range(switches_number):
            switches.append(lines[2 + i].replace('\n', '').replace(' ', ''))

        for i in range(2 + switches_number, 2 + switches_number + hosts_number):
            host_info = lines[i].split(',')
            host = {}
            host['name'] = host_info[0].replace(' ', '')
            host['ip'] = host_info[1].replace(' ', '')
            host['mac'] = host_info[2].replace('\n', '').replace(' ', '')
            hosts.append(host)
        hosts.remove(hosts[0])

        for i in range(2 + hosts_number + switches_number, len(lines)):
            link_info = lines[i].split(',')
            link = {}
            link['source'] = link_info[0].replace(' ', '')
            link['dest'] = link_info[1].replace(' ', '')
            link['bandwidth'] = link_info[2].replace(' ', '')
            link['port1'] = link_info[3].replace(' ', '')
            link['port2'] = link_info[4].replace('\n', '').replace(' ', '')
            links.append(link)
        links.remove(links[0])


#The main controller class
class MyController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(MyController, self).__init__(*args, **kwargs)
        self.dijkstraCalculated = False
        self.topology_api_app = self
        self.seen = set()
        #Reading the topology input file

        self.myhosts = [{}]
        self.myswitches = []
        self.mylinks = [{}]
        file_name = 'topology.txt'
        read_information(file_name, self.myhosts, self.myswitches, self.mylinks)
     
        self.get_topology_data()
        os.system("rm -rf results")
        os.mkdir("results")
        self.startTime = time.time()
        self.switchesFile = open("results/switchUpdatedTime.txt", "w+")
        self.dijkstraPathsFile = open("results/dijkstraPaths.txt", "w+")
        self.node_to_node_file = open("results/node-to-node.txt", "w")

    #This function adds a flow to a switch so the switch will know the path and will not ask the controller again
    def install_path(self, datapath, in_port, dst, src, actions):
        ofproto = datapath.ofproto
        #Making a match that determines switch and port we want to add flow on it
        match = datapath.ofproto_parser.OFPMatch(
            in_port=in_port,
            dl_dst=haddr_to_bin(dst), dl_src=haddr_to_bin(src))
        #Making a mod witch is the message we want to send the switch and contains the action adding flow to it
        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, match=match, cookie=0,
            command=ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
            priority=ofproto.OFP_DEFAULT_PRIORITY,
            flags=ofproto.OFPFF_SEND_FLOW_REM, actions=actions)
        #Sendig the message to the switch
        datapath.send_msg(mod)

    #With the event of recieving new packet, handles it
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        global paths, hostTopo
        #Extracting information like packet, protocols, src, dst, etc from event
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        #If the packet is type of LLDP we drop it as they are to get information about state of switches and links that we dont need
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        dst = eth.dst
        src = eth.src
        dpid = datapath.id
        outPort = None
        ss, dd = "-", "-"
        #Using mac address of the destination to find out if is main packet or not
        if(dst[:15] != '00:00:00:00:00:'):
            #This part is for packets that are not main packets and should be broadcasted, like DNS packets of mininet
            #To handle loops in the topology, for when these packets are broadcasted, the packets are dumped to string
            #If the packet had been seen on this switch before, we drop the packet as it is looping in the network and had been here before
            dumped = pickle.dumps(pkt)
            if((dpid, dumped) in self.seen):
                return
            #Add the packet to seen set to know not to flood it again
            self.seen.add((dpid, dumped))
            outPort = ofproto.OFPP_FLOOD
        else:
            #This part is for main packets
            #If the dijkstra paths have not been calculated, they will be
            if(self.dijkstraCalculated == False):
                self.find_path()
                self.dijkstraCalculated = True
            #Find the hosts id in src and dst and the switches they are connected to based on the mac address
            ss, srcId = self.get_mac_by_hostid(src)
            dd, dstId = self.get_mac_by_hostid(dst)
            if(srcId == dstId):
                #If the src and the dst hosts are connected to the same switch, the out port will be the port that connects to the dst host
                outPort = dd[2]
            else:
                #Path found from dijkstra from src to dst
                p = paths[srcId][dstId]
                path = p.split('-')
                if(str(dpid) == path[-1]):
                    #If the switch is the last switch in the path, the out port will be the port that connects switch to the host
                    outPort = dd[2]
                else:
                    #If the switch is a middle switch in the path, the out port will be the port that connects this switch to the next switch in the path by seeing the information of links
                    for i in range(len(path) - 1):
                        if(path[i] == str(dpid)):
                            #Using get_link to get all links information
                            linksList = get_link(self.topology_api_app, None)
                            for link in linksList:
                                if((int(path[i]) == link.src.dpid) and (int(path[i+1]) == link.dst.dpid)):
                                    outPort = link.src.port_no
                message = "Packet recieved on switch s{switch} on port {in_port} with source h{source} "
                message += "and destination h{dest} and the shortest path is {path} and the output "
                message += "port determined is {out_port}"
                print(message.format(switch=dpid, in_port=msg.in_port, source=ss[0], dest=dd[0], path=p, out_port=outPort))
                self.node_to_node_file.write("h{source},h{dest},{t},{path}\n".format(source=ss[0], dest=dd[0],
                    t=str(time.time() - self.startTime), path=p))
        #The action should be done on the switch whitch containes the output port of the packet
        actions = [datapath.ofproto_parser.OFPActionOutput(outPort)]
        if outPort != ofproto.OFPP_FLOOD:
            #Adding this found out port to the switch to not ask the controller again
            self.install_path(datapath, msg.in_port, dst, src, actions)
            self.switchesFile.write(str(dpid) + "," + str(time.time() - self.startTime) + "\n")
            self.switchesFile.flush()
        #Sending the main packet that is recieved by the switch, back to it so it can send it on it's out port
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath, buffer_id=msg.buffer_id, in_port=msg.in_port,
            actions=actions, data=data)
        #Sending the message
        datapath.send_msg(out)

    #Finds the host and the switch that it is connected to by the mac address
    def get_mac_by_hostid(self, mac):
        global hostTopo
        for h in hostTopo:
            if(hostTopo[h][3].strip() == mac.strip()):
                return hostTopo[h], hostTopo[h][0]


    #Reads the input file and saves the information in it in the right format
    def get_topology_data(self):
        global switchTopo, hostTopo

        for link in self.mylinks:
            if link['source'] in self.myswitches and link['dest'] in self.myswitches:
                temp1 = link['source'].replace('s', '')
                temp2 = link['dest'].replace('s', '')
                switchTopo.setdefault(temp1, {})
                switchTopo.setdefault(temp2, {})
                switchTopo[temp1][temp2] = float(link['bandwidth'])
                switchTopo[temp2][temp1] = float(link['bandwidth'])

            else:
                temp1 = link['source'].replace('h', '')
                temp2 = link['dest'].replace('s', '').replace('h', '')
                hostTopo.setdefault(temp1, [])
                hostTopo[temp1].append(temp2)
                hostTopo[temp1].append(float(link['bandwidth']))
                hostTopo[temp1].append(int(link['port2']))
                for h in self.myhosts:
                    if h['name'] == link['source']:
                        hostTopo[temp1].append(h['mac'])
                        break


    #This function initiates dijkstra between all pairs of hosts to find paths between them
    def find_path(self):
        global switchTopo, hostTopo, paths
        #Getting info about switches
        switchesList = get_switch(self.topology_api_app, None)
        switches = [switch.dp.id for switch in switchesList]
        #Finding path for each pair
        for i in range(len(switches) - 1):
            for j in range(i+1, len(switches)):
                srcId = str(switches[i])
                dstId = str(switches[j])
                distances = {}
                predecessors = {}
                #First, the distances of all nodes are inf and their parents are not determined
                for switch in switchTopo:
                    distances[switch] = float("inf")
                    predecessors[switch] = "-"
                #Distance of src is zero
                distances[srcId] = 0
                #Calling dijkstra to find path between these two
                p1, p2 = dijkstra(srcId, srcId, dstId, [], distances, predecessors)
                paths.setdefault(srcId, {})
                paths.setdefault(dstId, {})
                #Saving the found path
                paths[srcId][dstId] = p1
                paths[dstId][srcId] = p2
        #Printing all the found paths
        print('Dijkstra paths between switches:')
        for i in paths:
            for j in paths[i]:
                self.dijkstraPathsFile.write("Path from switch sw{} to sw{} -> {}\n".format(i, j, paths[i][j]))
                self.dijkstraPathsFile.flush()
