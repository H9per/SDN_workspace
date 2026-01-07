from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel
from functools import partial

class MyCustomTopo( Topo ):
    "Simple topology example."

    def build( self ):
        "Create custom topo."

        # 1. 添加交换机 (Add switches) - Total 18 switches
        switches = {}
        for i in range(1, 19):
            switches[f's{i}'] = self.addSwitch(f's{i}')

        # 2. 添加主机 (Add hosts)
        h1 = self.addHost( 'h1', ip='10.0.0.1' )
        h2 = self.addHost( 'h2', ip='10.0.0.2' )
        h3 = self.addHost( 'h3', ip='10.0.0.3' )

        # 3. 构建拓扑结构 (Build Topology)

        # --- 头部 (Head) ---
        # h3 -> s1 -> s2
        self.addLink( h3, switches['s1'] )
        self.addLink( switches['s1'], switches['s2'] )

        # --- 梯形主体 (Ladder Body) ---
        # s2 分流到 s3(左) 和 s4(右)
        self.addLink( switches['s2'], switches['s3'] )
        self.addLink( switches['s2'], switches['s4'] )

        # 梯形横向链路 (Horizontal rungs)
        ladder_pairs = [(3,4), (5,6), (7,8), (9,10)]
        for l, r in ladder_pairs:
            self.addLink( switches[f's{l}'], switches[f's{r}'] )

        # 梯形纵向链路 (Vertical rails)
        # s3->s5->s7->s9 (左侧)
        self.addLink( switches['s3'], switches['s5'] )
        self.addLink( switches['s5'], switches['s7'] )
        self.addLink( switches['s7'], switches['s9'] )
        
        # s4->s6->s8->s10 (右侧)
        self.addLink( switches['s4'], switches['s6'] )
        self.addLink( switches['s6'], switches['s8'] )
        self.addLink( switches['s8'], switches['s10'] )

        # --- 连接主体到腿部 ---
        self.addLink( switches['s9'], switches['s11'] )  # 左侧连接
        self.addLink( switches['s10'], switches['s12'] ) # 右侧连接

        # --- 左腿 (Left Leg - Diamond) ---
        # s11(顶) -> s13(左), s14(右) -> s17(底)
        self.addLink( switches['s11'], switches['s13'] )
        self.addLink( switches['s11'], switches['s14'] )
        self.addLink( switches['s13'], switches['s17'] )
        self.addLink( switches['s14'], switches['s17'] )
        # 连接主机 h2
        self.addLink( h2, switches['s17'] )

        # --- 右腿 (Right Leg - Diamond) ---
        # s12(顶) -> s15(左), s16(右) -> s18(底)
        self.addLink( switches['s12'], switches['s15'] )
        self.addLink( switches['s12'], switches['s16'] )
        self.addLink( switches['s15'], switches['s18'] )
        self.addLink( switches['s16'], switches['s18'] )
        # 连接主机 h1
        self.addLink( h1, switches['s18'] )

        # --- 桥接 (Bridge) ---
        # 连接两腿内侧的交换机 (s14 和 s15)
        self.addLink( switches['s14'], switches['s15'] )

def run():
    # 构建拓扑
    topo = MyCustomTopo()
    
    # 使用 OpenFlow 1.3 协议
    switch = partial( OVSKernelSwitch, protocols='OpenFlow13' )

    # 初始化 Mininet
    # build=False: 让我们手动添加控制器后再构建
    # autoSetMacs=True: 对应 --mac 参数，设置简单的 MAC 地址
    net = Mininet( topo=topo,
                   build=False,
                   ipBase='10.0.0.0/8',
                   autoSetMacs=True,
                   switch=switch )

    # 添加控制器 (对应 --controller=remote,ip=127.0.0.1,port=6653)
    c0 = net.addController( 'c0', controller=RemoteController, ip='127.0.0.1', port=6653 )

    # 构建网络
    net.build()

    # 启动网络
    net.start()

    # 发送免费 ARP 以快速通告主机位置，并在控制器注册
    print( "*** Sending Gratuitous ARP to pre-populate controller tables..." )
    for host in net.hosts:
        # -U 更新邻居ARP缓存 (Gratuitous ARP)
        # -c 1 发送一次
        host.cmd(f'arping -U -c 1 -I {host.name}-eth0 {host.IP()}')

    print( "*** Topology is up, press Ctrl-D to exit" )
    
    # 进入命令行界面
    CLI( net )
    
    net.stop()

if __name__ == '__main__':
    setLogLevel( 'info' )
    run()