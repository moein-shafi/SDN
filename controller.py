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
from collections import defaultdict

class MyController(app_manager.RyuApp):
    """
    This class is the main implementation of the controller
    """
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(MyController, self).__init__(*args, **kwargs)
        self.dijkstraIsCalculated = False
        self.topology_api_app = self
        self.seen = set()
        self.switchTopo = {}
        self.hostsTopology = {}
        self.paths = {}

        self.allHosts = [{}]
        self.allSwitches = []
        self.allLinks = [{}]
        self.read_information('topology.txt', self.allHosts, self.allSwitches, self.allLinks)
     
        self.get_topology_data()
        os.system("rm -rf results")
        os.mkdir("results")
        self.startTime = time.time()
        self.switchesFile = open("results/switch_flow_table_update_times.txt", "w+")
        self.node_to_node_file = open("results/node-to-node.txt", "w")

    def install_path(self, datapath, in_port, dst, src, actions):
        """
        This function adds a flow to a switch so the switch will know the path and will not ask the controller again
        """
        ofproto = datapath.ofproto
        match = datapath.ofproto_parser.OFPMatch(
            in_port=in_port,
            dl_dst=haddr_to_bin(dst), dl_src=haddr_to_bin(src))
        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, match=match, cookie=0,
            command=ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
            priority=ofproto.OFP_DEFAULT_PRIORITY,
            flags=ofproto.OFPFF_SEND_FLOW_REM, actions=actions)
        datapath.send_msg(mod)


    def read_information(self, file_name: str, hosts: list, switches: list, links: list):
        with open(file_name, 'r') as reader:
            lines = reader.readlines()
            switch_numbers = int(lines[0].replace('\n', ''))
            host_numbers = int(lines[1].replace('\n', ''))
            for i in range(switch_numbers):
                switches.append(lines[2 + i].replace('\n', '').replace(' ', ''))

            for i in range(2 + switch_numbers, 2 + switch_numbers + host_numbers):
                host_info = lines[i].split(',')
                host = {}
                host['name'] = host_info[0].replace(' ', '')
                host['ip'] = host_info[1].replace(' ', '')
                host['mac'] = host_info[2].replace('\n', '').replace(' ', '')
                hosts.append(host)
            hosts.remove(hosts[0])

            for i in range(2 + host_numbers + switch_numbers, len(lines)):
                link_info = lines[i].split(',')
                link = {}
                link['source'] = link_info[0].replace(' ', '')
                link['dest'] = link_info[1].replace(' ', '')
                link['bandwidth'] = link_info[2].replace(' ', '')
                link['port1'] = link_info[3].replace(' ', '')
                link['port2'] = link_info[4].replace('\n', '').replace(' ', '')
                links.append(link)
            links.remove(links[0])


    def dijkstra(self, src, x, dest, visited, distances, predecessors):
        """
        This function applies the dijkstra algorithm and finds the shortest path between two hosts
        """
        if x == dest:
            path = []
            temp = dest
            while(temp != src):
                path.append(temp)
                temp = predecessors[temp]
            path.append(src)
            return "-".join(path[::-1]), "-".join(path)
        else:
            for neighbor in self.switchTopo[x]:
                if neighbor not in visited:
                    new_distance = distances[x] + self.switchTopo[x][neighbor]
                    if new_distance < distances[neighbor]:
                        distances[neighbor] = new_distance
                        predecessors[neighbor] = x

            visited.append(x)
            minimum = float("inf")
            minimumNode = None
            for k in self.switchTopo:
                if((k not in visited) and (distances[k] < minimum)):
                    minimum = distances[k]
                    minimumNode = k
            return self.dijkstra(src, minimumNode, dest, visited, distances, predecessors)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """
        When recieving new packet, this function handles it
        """
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id
        outPort = None
        ss, dd = "-", "-"

        if(dst[:15] != '00:00:00:00:00:'):
            dumped = pickle.dumps(pkt)
            if((dpid, dumped) in self.seen):
                return
            self.seen.add((dpid, dumped))
            outPort = ofproto.OFPP_FLOOD
        else:
            if(self.dijkstraIsCalculated == False):
                self.find_path()
                self.dijkstraIsCalculated = True
            ss, srcId = self.get_mac_by_hostid(src)
            dd, dstId = self.get_mac_by_hostid(dst)
            if(srcId == dstId):
                outPort = dd[2]
            else:
                p = self.paths[srcId][dstId]
                path = p.split('-')
                if(str(dpid) == path[-1]):
                    outPort = dd[2]
                else:
                    for i in range(len(path) - 1):
                        if(path[i] == str(dpid)):
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

        actions = [datapath.ofproto_parser.OFPActionOutput(outPort)]
        if outPort != ofproto.OFPP_FLOOD:
            self.install_path(datapath, msg.in_port, dst, src, actions)
            self.switchesFile.write(str(dpid) + "," + str(time.time() - self.startTime) + "\n")
            self.switchesFile.flush()
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath, buffer_id=msg.buffer_id, in_port=msg.in_port,
            actions=actions, data=data)
        datapath.send_msg(out)

    def get_mac_by_hostid(self, mac):
        """
        Finds the host and the switch that is connected to by the mac address
        """
        for h in self.hostsTopology:
            if(self.hostsTopology[h][3].strip() == mac.strip()):
                return self.hostsTopology[h], self.hostsTopology[h][0]

    def get_topology_data(self):
        """
        Reads the input file and saves the information in it in the right format
        """
        for link in self.allLinks:
            if link['source'] in self.allSwitches and link['dest'] in self.allSwitches:
                newSrcLink = link['source'].replace('s', '')
                newDstLink = link['dest'].replace('s', '')
                self.switchTopo.setdefault(newSrcLink, {})
                self.switchTopo.setdefault(newDstLink, {})
                self.switchTopo[newSrcLink][newDstLink] = float(link['bandwidth'])
                self.switchTopo[newDstLink][newSrcLink] = float(link['bandwidth'])

            else:
                newSourceLink = link['source'].replace('h', '')
                newDstLink = link['dest'].replace('s', '').replace('h', '')
                self.hostsTopology.setdefault(newSourceLink, [])
                self.hostsTopology[newSourceLink].append(newDstLink)
                self.hostsTopology[newSourceLink].append(float(link['bandwidth']))
                self.hostsTopology[newSourceLink].append(int(link['port2']))
                for host in self.allHosts:
                    if host['name'] == link['source']:
                        self.hostsTopology[newSourceLink].append(host['mac'])
                        break


    def find_path(self):
        """
        This function initiates dijkstra between all pairs of hosts to find paths between them
        """

        switchesList = get_switch(self.topology_api_app, None)
        switches = [switch.dp.id for switch in switchesList]
        for i in range(len(switches) - 1):
            for j in range(i+1, len(switches)):
                srcId = str(switches[i])
                dstId = str(switches[j])
                distances = {}
                predecessors = {}
                for switch in self.switchTopo:
                    distances[switch] = float("inf")
                    predecessors[switch] = "-"
                distances[srcId] = 0
                p1, p2 = self.dijkstra(srcId, srcId, dstId, [], distances, predecessors)
                self.paths.setdefault(srcId, {})
                self.paths.setdefault(dstId, {})
                self.paths[srcId][dstId] = p1
                self.paths[dstId][srcId] = p2

