#!/usr/bin/python3

import os
import random
import subprocess
import sys
import threading
import time

from datetime import datetime
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.node import *
from mininet.cli import CLI
from mininet.log import *
from mininet.link import *


class MyTopo(Topo):
    def __init__(self, hosts_info: list, switches_info: list, links_info: list):
        Topo.__init__(self)
        self.hosts_info = hosts_info
        self.switches_info = switches_info
        self.links_info = links_info
        self.myhosts = []
        self.myswitches = []
        self.add_hosts()
        self.add_switches()
        self.add_links()


    def add_hosts(self):
        for host in self.hosts_info:
            self.myhosts.append(self.addHost(host['name'],
                              cls=Host,
                              ip=host['ip'],
                              mac=host['mac'],
                              defaultRoute=None))


    def add_switches(self):
        for switch in self.switches_info:
            self.myswitches.append(self.addSwitch(switch))


    def add_links(self):
        for link in self.links_info:
            source = self.myhosts[0]
            dest = self.myhosts[0]
            
            # first find the source and dest and then add links
            for host in self.myhosts:
                if host == link['source']:
                    source = host
                if host == link['dest']:
                    dest = host

            for switch in self.myswitches:
                if switch == link['source']:
                    source = switch
                if switch == link['dest']:
                    dest = switch

            self.addLink(source,
                         dest,
                         port1=int(link['port1']),
                         port2=int(link['port2']),
                         cls=TCLink,
                         bw=int(link['bandwidth']))


class MyNetworkHandler(object):
    def __init__(self, myhosts: list, net):
        self.myhosts = myhosts
        self.net = net
        self.threads_list = []
        self.time_unit = 0.1
        self.send_packet_file =  open("results/send_packets.txt", "w+")


    def handle(self):
        self.lock = threading.Lock()
        self.change_bw_thread = threading.Thread(target=self.change_links_bandwidth)
        self.threads_list.append(self.change_bw_thread)
        self.change_bw_thread.start()
        start_time = time.time()
        for i in range(25):
            thread = threading.Thread(target=self.send_packet, args=[i])
            thread.start()
            self.threads_list.append(thread)

        time.sleep(60)
        for thread in self.threads_list:
            thread.join()


    def send_packet(self, turn):
        time.sleep(turn * self.time_unit)
        for i in range(24):
            for myhost in self.myhosts:
                host = self.net.get(myhost)
                dest_host = random.choice(list(set(self.myhosts) - set(myhost)))
                dest_ip = self.net.get(dest_host).IP()
                start_time = time.time()
                command = 'hping3 -c 1 -d 100000 {ip} &'.format(ip=dest_ip)
                host.cmd(command)
                end_time = time.time()
                self.send_packet_file.write(host.IP().split(".")[-1] + "," + dest_host.replace('h', '') + "," +
                        str(end_time - start_time) + "\n")
                self.send_packet_file.flush()

            if i < 23:
                time.sleep(2.5)


    def change_links_bandwidth(self):
        sleep(30)
        nodes = self.net.switches + self.net.hosts
        print(">>> Changing Bandwidth...")
        print(50 * '=')
        for node in nodes:
            for interface in node.intfList():
                if interface.link:
                    new_bandwidth = random.uniform(1, 5)
                    interface.link.intf1.config(bw=new_bandwidth)
                    interface.link.intf2.config(bw=new_bandwidth)


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

        """ Theses lines are just for testing. uncomment them to test the
            property of file read function.

        for s in switches:
            print(s)
        for h in hosts:
            print(h)
        for l in links:
            print(l) """


def main():
    print(50 * '=')
    print('Group Info:')
    print('\tAli Khoshtinat          810196462')
    print('\tMohammad Moein Shafi    810196492')
    print(50 * '=')
    hosts = [{}]
    switches = []
    links = [{}]
    file_name = 'topology.txt'
    print('>>> Reading Information...')
    read_information(file_name, hosts, switches, links)
    print(50 * '=')
    print('>>> Starting Network...')

    for i in range(5): 
        print(50 * '=')
        print(">>> Round number #" + str(i))
        print(50 * '=')
        topo = MyTopo(hosts, switches, links)
        net = Mininet(topo, controller=lambda name: RemoteController(name,
                    ip= '127.0.0.1', protocol= 'tcp', port= 6635), autoSetMacs= True)
        myhandler = MyNetworkHandler(topo.myhosts, net)
        net.start()
        myhandler.handle()
        CLI(net)
        net.stop()


if __name__ == '__main__':
    main()
