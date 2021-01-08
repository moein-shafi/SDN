-  How to check flow table: (mininet terminal)

> dpctl dump-flows -O OpenFlow13

-  How to run Ryu controller:

> ryu-manager --observe-links --ofp-tcp-listen-port 6635 [arbitrary port] ./controller.py

-  How to run mininet program:

> - Cleaning before run:
>>   sudo mn -c
> - Running mininet:
>>   sudo -E python networkTopology.py

- How to run processor file:

> python3 Processor.py

- read mininet code if you want:
> - to change bandwidth of links in real time
> - to run commands from python file
> - to schedule packet sending

- read ryu controller code if you want:
> - to impelement dijkstra algorithm
> - to do link discovery
> - to get ipv4 headers
