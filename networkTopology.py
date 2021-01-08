                                                                                             
import subprocess
import random
import sys
import threading
import time

from datetime import datetime
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
from mininet.node import Controller, RemoteController, OVSController
from mininet.node import CPULimitedHost, Host, Node
from mininet.node import OVSKernelSwitch, UserSwitch
from mininet.node import IVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink, Intf


setLogLevel( 'info' )
hostList = 7 * [0]

class MyTopo(Topo):

    def __init__(self, ipBase='10.0.0.0/8'):
        Topo.__init__(self)

        
        info( '*** Add switches\n')
        self.s1 = self.addSwitch('s1')
        self.s2 = self.addSwitch('s2')
        self.s3 = self.addSwitch('s3')
        self.s4 = self.addSwitch('s4')


        info( '*** Add hosts\n')
        global hostList
        for i in range(1, 8):
            hostList[i-1] = self.addHost('h%s'%i, cls=Host, ip='10.0.0.%s'%i,mac='00:00:00:00:00:0%s'%i, defaultRoute=None)

        self.addLinks()

    def addLinks(self):
        info( '*** Add links\n')
        self.addLink(hostList[0], self.s1, cls = TCLink, bw = random.uniform(1,5))
        self.addLink(hostList[1], self.s2, cls = TCLink, bw = random.uniform(1,5))
        self.addLink(hostList[2], self.s3, cls = TCLink, bw = random.uniform(1,5))
        self.addLink(hostList[3], self.s3, cls = TCLink, bw = random.uniform(1,5))
        self.addLink(hostList[4], self.s4, cls = TCLink, bw = random.uniform(1,5))
        self.addLink(hostList[5], self.s4, cls = TCLink, bw = random.uniform(1,5))
        self.addLink(hostList[6], self.s4, cls = TCLink, bw = random.uniform(1,5))
        # self.addLink(self.s2,self.s1, cls = TCLink, bw = random.uniform(1,5))
        self.addLink(self.s3,self.s1, cls = TCLink, bw = random.uniform(1,5))
        self.addLink(self.s2,self.s3, cls = TCLink, bw = random.uniform(1,5))
        self.addLink(self.s3,self.s4, cls = TCLink, bw = random.uniform(1,5))
        # self.addLink(self.s4,self.s2, cls = TCLink, bw = random.uniform(1,5))


def changeBandwith( node ):
    "Helper function: dump connections to node"
    for intf in node.intfList():
        info( ' %s:'%intf )
        if intf.link:
            randomNumber = random.uniform(1,5)
            intfs = [ intf.link.intf1, intf.link.intf2 ]
            intfs[0].config(bw=randomNumber)
            intfs[1].config(bw=randomNumber)
        else:
            info( ' \n' )

def manageLinks():
    nodes = net.switches + net.hosts
    for node in nodes:
        changeBandwith(node)

def runCmd(h, cmdStr):
    h.cmd(cmdStr)

def sendTcpPackets():
    t_list = []
    for host in hostList:
        h = net.get(host)
        targetHost = random.choice(list(set(hostList) - set(host)))
        target_ip = net.get(targetHost).IP()
        cmdStr = 'hping3 -c 1 -d 100000 %s&'%target_ip
        t = threading.Thread(target=runCmd, args=[h, cmdStr])
        t.start()
        t_list.append(t)
    for t in t_list:
        t.join()


def run():
    timeCounter = 0
    unit = 0.1
    info('start running')
    # print(datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
    while timeCounter * unit < 60:
        time.sleep(unit)
        sendTcpPackets()
        timeCounter += 1
        if timeCounter * unit % 10 == 0:
            manageLinks()

    # print(datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
    info('end of execution')

info( '*** Starting network\n')

            

for i in range(5): 
    print('round ', i) 
    topo = MyTopo()
    net = Mininet(topo, controller=lambda name: RemoteController(name,
                ip= '127.0.0.1', protocol= 'tcp', port= 6635), autoSetMacs= True)
    net.start()
    time.sleep(7)
    run()
    # CLI(net)
    net.stop()
    time.sleep(15)