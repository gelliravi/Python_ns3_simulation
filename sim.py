import sys
import time
import ns.applications
import ns.core
import ns.internet
import ns.network
import ns.point_to_point
import ns.flow_monitor
import ns.point_to_point_layout
import matplotlib.pyplot as plt
import numpy as np
import sys


"""
Network Topology:

+----+
| C1 |------------+
+----+            |
                  |
+----+            |
| C2 |------------|
+----+            |
                  |
...            +-----+        +--------+
...            | hub |--------| server |
               +-----+        +--------+
+----+            |
|CN-1|------------|
+----+            |
                  |
+----+            |
| CN |------------+
+----+
"""


if len(sys.argv < 2):
    print "Error: Too few arguemtns"
    print "Usage: python <filename> <datarate in Mbps>"
    print "eg: python ns_sim.py 5"
    sys.exit(2)


# set random seed
ns.core.RngSeedManager.SetSeed(int(time.time() * 1000 % (2**31)))


cmd = ns.core.CommandLine()
cmd.rate = int(sys.argv[1])*100000
NR_OF_NODES = 64 + 1 # Clients + 1 server
TPS = []
QUEUE_LENGTH = 100
cmd.interval = 0.5
cmd.AddValue ("latency", "P2P link Latency in miliseconds")
cmd.AddValue ("rate", "P2P data rate in bps")
cmd.AddValue ("interval", "UDP client packet interval")
cmd.Parse(sys.argv)
print "******* SIMULATION IS SETTING UP... *********"
#######################################################################################
cmd.latency = 2

# set length of queue
ns.core.Config.SetDefault("ns3::DropTailQueue::MaxPackets", ns.core.UintegerValue(QUEUE_LENGTH))

pointToPoint = ns.point_to_point.PointToPointHelper()
pointToPoint.SetDeviceAttribute("Mtu",ns.core.UintegerValue(1500))
pointToPoint.SetDeviceAttribute("DataRate",ns.network.DataRateValue(ns.network.DataRate(int(cmd.rate))))
pointToPoint.SetChannelAttribute("Delay",
                                ns.core.TimeValue(ns.core.MilliSeconds(int(cmd.latency))))


star = ns.point_to_point_layout.PointToPointStarHelper(NR_OF_NODES,pointToPoint) # create star topology
hub = star.GetHub()


em = ns.network.RateErrorModel()
em.SetAttribute("ErrorUnit", ns.core.StringValue("ERROR_UNIT_PACKET"))
em.SetAttribute("ErrorRate", ns.core.DoubleValue(0.01))



# install internet stack
internet_stack = ns.internet.InternetStackHelper()
star.InstallStack(internet_stack)


# Assign addresses
address = ns.internet.Ipv4AddressHelper()
address.SetBase(ns.network.Ipv4Address("10.1.0.0"), ns.network.Ipv4Mask("255.255.192.0")) # 16382 addresses
star.AssignIpv4Addresses(address)

ns.internet.Ipv4GlobalRoutingHelper.PopulateRoutingTables()

server_node = star.GetSpokeNode(0)
# Set server error rate
snd = server_node.GetDevice(0)
snd.SetReceiveErrorModel(em)


echo_server = ns.applications.UdpEchoServerHelper(9)
server_app = echo_server.Install(server_node)
server_app.Start(ns.core.Seconds(0.0))
server_app.Stop(ns.core.Seconds(200.0))


for i in range(1,star.SpokeCount()):
    server_address = star.GetSpokeIpv4Address(0)
    echo_client = ns.applications.UdpEchoClientHelper(server_address,9)
    echo_client.SetAttribute("MaxPackets",ns.core.UintegerValue(10000))
    echo_client.SetAttribute("Interval",ns.core.TimeValue(ns.core.Seconds(float(cmd.interval))))
    echo_client.SetAttribute("PacketSize",ns.core.UintegerValue(508))
    client_node = star.GetSpokeNode(i)
    client_address = star.GetSpokeIpv4Address(i)
    client_app = echo_client.Install(client_node)
    client_app.Start(ns.core.Seconds(5.0))
    client_app.Stop(ns.core.Seconds(95.0))
    print "Created client application: " + str(client_address) + " -> " + str(server_address)


flowmon_helper = ns.flow_monitor.FlowMonitorHelper()
monitor = flowmon_helper.InstallAll()
monitor = flowmon_helper.GetMonitor()


# 0.0005 = 0.5 ms
monitor.SetAttribute("DelayBinWidth", ns.core.DoubleValue(0.005))


#######################################################################################
# RUN THE SIMULATION
#
# We have to set stop time, otherwise the flowmonitor causes simulation to run forever

ns.core.Simulator.Stop(ns.core.Seconds(300.0))
ns.core.Simulator.Run()
monitor.CheckForLostPackets()

classifier = flowmon_helper.GetClassifier()
tot_lost = 0
tot_sent = 0

tot_delay={}
tot_p = 0
packet_lost = 0

for flow_id, flow_stats in monitor.GetFlowStats():
  delay_histogram = flow_stats.delayHistogram
  for i in range(delay_histogram.GetNBins()):
      key = str(1000*delay_histogram.GetBinStart(i))+"-"+str(1000*delay_histogram.GetBinEnd(i))
      if key in tot_delay:
          tot_delay[key] = tot_delay[key] + delay_histogram.GetBinCount(i)
      else:
          tot_delay[key] = delay_histogram.GetBinCount(i)


  print "---------------------------"  
  t = classifier.FindFlow(flow_id)
  proto = {6: 'TCP', 17: 'UDP'} [t.protocol]
  

  
  print ("FlowID: %i (%s %s/%s --> %s/%i)" % 
          (flow_id, proto, t.sourceAddress, t.sourcePort, t.destinationAddress, t.destinationPort))
  print "LOST " + str(flow_stats.lostPackets) + " packets"  
  print "Sent " + str(flow_stats.txPackets) + " packets"
  print "Active: " + str(flow_stats.timeFirstTxPacket.GetSeconds()) + " - " + str(flow_stats.timeLastRxPacket.GetSeconds())
  tot_lost = tot_lost + flow_stats.lostPackets
  tot_sent = tot_sent + flow_stats.txPackets 



def get_key(key):
    k = key.split('-')
    o = float(k[0])
    return o


lx = sorted(tot_delay.items(), key=lambda t: get_key(t[0]))
ks = [] # strings
vs = [] # ints
ok_count = 0
for key in lx:
    cnt = str(tot_delay[key[0]])
    intr = (key[0])[:2]
    print key[0] + "ms: " + cnt
    if tot_delay[key[0]] != 0:
        ks.append(str(key[0]))
        vs.append(tot_delay[key[0]])
    if (intr[1:2]) == ".":
        ok_count = ok_count + int(cnt)
    # comparing intr to (including) upper   bound of intervall
    elif int(intr) < 50 and len(key[0]) < 10:
        ok_count = ok_count + int(cnt)
       
print "TOTAL PACKETS: " + str(tot_sent)
print "ok count: " + str(ok_count)

print "===================== Results ========================"
print "Number of clients: " + str(NR_OF_NODES-1)
print "DataRate: " + str(float(sys.argv[1])/10.0) + "Mbps"
print "Packets w. ok delay: " + str(float(ok_count)/float(tot_sent)*100) + "%"
print "Loss: " + str((float(tot_lost)/float(tot_sent))*100.0) + "%"
print "Queue Length: " + str(QUEUE_LENGTH)
print "Server Address: " + str(server_address)
print "Hub Address: " + str(star.GetHubIpv4Address(0))
print "TOTAL LOST: " + str(tot_lost) + " packets"
print "TOTAL SENT: " + str(tot_sent) + " packets"
print "======================================================"
ns.core.Simulator.Destroy()
