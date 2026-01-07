import os
import sys
import argparse
from mininet.net import Mininet
from mininet.topo import Topo
from mininet.log import setLogLevel, info
from mininet.cli import CLI
from mininet.node import Switch, Host, RemoteController

class ONOSBmv2Switch(Switch):
    """BMv2 Switch with P4Runtime support"""
    def __init__(self, name, thrift_port=9090, grpc_port=50001, device_id=1, **kwargs):
        Switch.__init__(self, name, **kwargs)
        self.thrift_port = thrift_port
        self.grpc_port = grpc_port
        self.device_id = device_id
        self.log_file = '/tmp/bmv2_%s.log' % name

    def start(self, controllers):
        info("Starting BMv2 switch %s...\n" % self.name)
        args = [
            'simple_switch_grpc',
            '--device-id', str(self.device_id),
            '--thrift-port', str(self.thrift_port),
            '--log-file', self.log_file,
            '--no-p4' # 重要：不带 P4 程序启动，等待 ONOS 推送 Pipeconf
        ]
        
        # 配置 gRPC
        # --grpc-server-addr 默认 0.0.0.0:50001
        args.append('--')
        args.append('--grpc-server-addr')
        args.append('0.0.0.0:' + str(self.grpc_port))
        args.append('--cpu-port')
        args.append('255')

        # 端口映射: -i 1@s1-eth1
        for port, intf in self.intfs.items():
            if not intf.IP():
                args.append('-i')
                args.append(str(port) + '@' + intf.name)

        # 运行 simple_switch_grpc
        self.cmd(' '.join(args) + ' > /dev/null 2>&1 &')

    def stop(self):
        info("Stopping BMv2 switch %s...\n" % self.name)
        self.cmd('kill %simple_switch_grpc')
        self.deleteIntfs()

class SimpleTopology(Topo):
    """2 hosts, 1 P4 switch"""
    def build(self):
        h1 = self.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
        h2 = self.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
        s1 = self.addSwitch('s1', cls=ONOSBmv2Switch, grpc_port=50001, device_id=1)
        
        self.addLink(h1, s1)
        self.addLink(h2, s1)

def main():
    setLogLevel('info')
    
    topo = SimpleTopology()
    # 使用 RemoteController 连接本地 ONOS
    net = Mininet(topo=topo, controller=lambda name: RemoteController(name, ip='127.0.0.1'))
    
    net.start()
    
    info("\nNetowrk started. Please push netcfg.json to ONOS now.\n")
    info("Press Enter in CLI after ONOS config is done.\n")
    
    CLI(net)
    net.stop()

if __name__ == '__main__':
    main()
