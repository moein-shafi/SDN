from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet, arp, ipv4
from ryu.lib.packet import ether_types
from ryu.lib import mac
from ryu.lib.mac import haddr_to_bin
from ryu.controller import mac_to_port
from ryu.ofproto import inet
from ryu.lib.packet import icmp
from ryu.ofproto import ether
from ryu.topology import event, switches
from ryu.topology.api import get_switch, get_link
from ryu.app.wsgi import ControllerBase
import array
from ryu.app.ofctl.api import get_datapath
import json
import copy
from datetime import datetime

def getTopology():
    topo = {}
    f = open('topology.json')
    data = json.load(f)
    for link in data:
        if link['port1'] not in topo:
            topo[link['port1']] = {}
        if link['port2'] not in topo:
            topo[link['port2']] = {}

        topo[link['port1']][link['port2']] = link['weight']
        topo[link['port2']][link['port1']] = link['weight']
    return topo

    

def find_min_distance(l, distances):
    if not l:
        return
    minNode = l[0]
    for n in l:
        if distances[n] < distances[minNode]:
            minNode = n 
    return minNode

def dijkstra(src, dest):
    graph = getTopology()

    if src not in graph:
        raise TypeError('The source node cannot be found')
    if dest not in graph:
        return []
    
    visited = {src}
    nodes = set(graph.keys())
    distances = {}
    predecessors = {}

    distances[src] = 0
    predecessors[src] = src 

    for node in nodes:
        if node in graph[src]:
            distances[node] = graph[src][node]
            predecessors[node] = src
        else:
            distances[node] = float('inf')
    
    while nodes != visited:
        nextNode = find_min_distance(list(nodes-visited), distances)
        if nextNode == None:
            break
        visited.add(nextNode)
        for node in graph.get(nextNode, []):
            if distances[nextNode] + graph[nextNode][node] < distances[node]:
                distances[node] = distances[nextNode] + graph[nextNode][node]
                predecessors[node] = nextNode

    path = []
    n = dest
    while n != src:
        path.append(n)
        n = predecessors[n]
    path.append(src)
    path.reverse()
    return path
    

def dpid_hostLookup(lmac):
    host_locate = {1: {'00:00:00:00:00:01'}, 2: {'00:00:00:00:00:02'}, 3: {'00:00:00:00:00:03', '00:00:00:00:00:04'},
                    4: {'00:00:00:00:00:05', '00:00:00:00:00:06', '00:00:00:00:00:07'}}
    for dpid, mac in host_locate.items():
        if lmac in mac:
            return dpid
    return -1

class dijkstra_switch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(dijkstra_switch, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.dpid_to_port = {}
        self.flowRateFile = open('flowRate.tr', 'w')
        self.packetTrace = open('packetTrace.tr', 'w')

        # self.topo_raw_links = [
        #     {'src': {'dpid': 2, 'port_no': 2 }, 'dst':{'dpid': 3, 'port_no': 4}},
        #     {'src': {'dpid': 3, 'port_no': 3 }, 'dst':{'dpid': 1, 'port_no': 2}},
        #     {'src': {'dpid': 3, 'port_no': 5 }, 'dst':{'dpid': 4, 'port_no': 4}},
        #     {'src': {'dpid': 3, 'port_no': 4 }, 'dst':{'dpid': 2, 'port_no': 2}},
        #     {'src': {'dpid': 1, 'port_no': 2 }, 'dst':{'dpid': 3, 'port_no': 3}},
        #     {'src': {'dpid': 4, 'port_no': 4 }, 'dst':{'dpid': 3, 'port_no': 5}}
        # ]

    def log(self, msg, file):
        file.write(str(datetime.utcnow().strftime('%H:%M:%S.%f')[:-3]) + '\t' + msg + '\n')

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 2, match, actions)

    def add_flow(self, datapath, priority, match,actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst)
        datapath.send_msg(mod)
        self.log(str(datapath.id), self.flowRateFile)


    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        isTcp = False

        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        dst = eth.dst
        src = eth.src
        dpid = datapath.id        
        in_port = msg.match['in_port']
        self.mac_to_port.setdefault(dpid, {})

        self.mac_to_port[dpid][src] = in_port

        dst_dpid = dpid_hostLookup(dst)

        path = dijkstra(dpid, dst_dpid) 


        if len(path) == 0:
            out_port = ofproto.OFPP_FLOOD
            actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
        elif len(path) == 1:
            if dst in self.mac_to_port[dpid]:
                out_port = self.mac_to_port[dpid][dst]
            else:
                out_port = ofproto.OFPP_FLOOD

            actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
            if out_port != ofproto.OFPP_FLOOD:
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
                self.add_flow(datapath, 1, match, actions)
        else:
            next_dpid = path[1]
            out_port = self.getDpidPort(dpid, next_dpid)
            actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]


        for p in pkt.protocols:
            if hasattr(p,'protocol_name') and p.protocol_name == 'tcp':
                isTcp = True

        if isTcp:
            pkt_ipv4 = pkt.get_protocol(ipv4.ipv4)
            self.log( str(pkt_ipv4.identification) + ' ' + str(src) + ' ' + str(dst) + ' ' + str(path).replace(' ', '') , self.packetTrace)
            self.logger.info("in_port:%s, out_port: %s, path:%s", in_port, out_port, str(path))
            

        out = parser.OFPPacketOut(datapath=datapath,
                                  buffer_id=ofproto.OFP_NO_BUFFER,
                                  in_port=in_port, actions=actions,
                                  data=msg.data)
        datapath.send_msg(out)

    @set_ev_cls(event.EventSwitchEnter)
    def handler_switch_enter(self, ev):
        self.logger.info('switch entered')
        # The Function get_switch(self, None) outputs the list of switches.
        self.topo_raw_switches = copy.copy(get_switch(self, None))
        # The Function get_link(self, None) outputs the list of links.
        self.topo_raw_links = copy.copy(get_link(self, None))
        
    def getDpidPort(self, src_dpid, dst_dpid):
        for link in self.topo_raw_links:
            if (link.src.dpid == src_dpid and link.dst.dpid == dst_dpid):
                return link.src.port_no

        for l in self.topo_raw_links:
            print(l)
        self.logger.info('link between %s and %s does not exist', src_dpid, dst_dpid)


        
