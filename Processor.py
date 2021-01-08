import json
import matplotlib.pyplot as plt
from datetime import datetime


class Processor:

    def __init__(self):
        self.hosts = { '00:00:00:00:00:01' : 'h1', '00:00:00:00:00:02' : 'h2' , 
                       '00:00:00:00:00:03' : 'h3' , '00:00:00:00:00:04' : 'h4', 
                       '00:00:00:00:00:05' : 'h5' , '00:00:00:00:00:06' : 'h6' , 
                       '00:00:00:00:00:07' : 'h7'}
        

    def splitFile(self,filename):
        lines = []
        file = open(filename, 'r')
        line = file.readline()
        while line:
            lines.append(line.split())
            line = file.readline()
        return lines

    def writeToFile(self, filename, data):
        with open(filename, "w") as f:
            f.write(json.dumps(data, indent=2))

    def strToTime(self,string):
        return datetime.strptime(string, '%H:%M:%S.%f')

    def processPacketTrace(self):
        lines = self.splitFile('packetTrace.tr')
        packetTrace = {}
        startTimeInTotal = self.strToTime(lines[0][0])
        for line in lines:
            time = self.strToTime(line[0])
            ipv4Id = line[1]
            src = self.hosts[line[2]]
            dst = self.hosts[line[3]]
            path = line[4]

            if not (src,dst) in packetTrace:
                packetTrace[(src,dst)] = {}

            if not ipv4Id in packetTrace[(src,dst)]:
                packetTrace[(src,dst)][ipv4Id] = [path, time, 0]
            else:
                packetTrace[(src,dst)][ipv4Id][2] = (time - packetTrace[(src,dst)][ipv4Id][1]).total_seconds()

        data = {}
        for key in packetTrace:
            s = str(key[0]) + ' to ' + str(key[1])
            data[s] = {}
            for k in packetTrace[key]:
                if k != 0:
                    data[s][str(k)] = [packetTrace[key][k][0], str(packetTrace[key][k][2])] 

        self.writeToFile('packetHistory.json', data)
        self.processChart(packetTrace, startTimeInTotal)

    def processChart(self, packetTrace, start):
        pktTripTime = {}
        data = {}
        for key in packetTrace:
            if not key[0] in pktTripTime:
                pktTripTime[key[0]] = {}
            pktTripTime[key[0]][key[1]] = [0] * 50
            for k in packetTrace[key]:
                startTime = packetTrace[key][k][1]
                diff = (startTime - start).total_seconds() + packetTrace[key][k][2]
                d = int(diff // 10)
                if pktTripTime[key[0]][key[1]][d] == 0:
                    pktTripTime[key[0]][key[1]][d] = [packetTrace[key][k][2], 1]
                else:
                    pktTripTime[key[0]][key[1]][d][0] += packetTrace[key][k][2]
                    pktTripTime[key[0]][key[1]][d][1] += 1
        
        for src in pktTripTime:
            data[src] = {}
            for dst in pktTripTime[src]:
                data[src][dst] = [0] * 50
                for i in range(len(pktTripTime[src][dst])):
                    val = pktTripTime[src][dst][i]
                    if val != 0:
                        data[src][dst][i] = val[0] / val[1]

        x = range(50)
        for src in data:
            for dst in data[src]:
                plt.plot(x,data[src][dst], label=str(dst))
            plt.xlabel('Time(* 10s)')
            plt.ylabel('Avg Delivery Time')
            plt.title('from src ' + str(src))
            plt.legend()
            plt.show()
        

    def processFlowRate(self):
        lines = self.splitFile('flowRate.tr')
        flowTable = {}
        data = {}
        for line in lines:
            time = self.strToTime(line[0])
            dpid = int(line[1])
            if not dpid in flowTable:
                flowTable[dpid] = [time, time, 1]
            else:
                flowTable[dpid][1] = time
                flowTable[dpid][2] += 1
        
        for dpid in flowTable:
            k = flowTable[dpid]
            data[dpid] = k[2] / (((k[1]-k[0]).total_seconds())-60)
        self.writeToFile('flowDetail.json', data)

    def process(self):
        self.processPacketTrace()
        self.processFlowRate()



processor = Processor()
processor.process()