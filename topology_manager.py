import json
from collections import defaultdict, deque

class TopologyGraph:
    def __init__(self, links_data=None, hosts_data=None):
        """
        初始化拓扑图
        :param links_data: 包含链路信息的列表 (即 topo.json 的内容)
        :param hosts_data: 包含主机信息的列表
        """
        self.adj = defaultdict(dict)
        if links_data:
            self.load_from_data(links_data)
        if hosts_data:
            self.load_hosts(hosts_data)

    def load_from_data(self, links_data):
        """
        从链路数据构建图
        """
        self.adj.clear()
        for link in links_data:
            src_dev = link['src']['device']
            src_port = link['src']['port']
            dst_dev = link['dst']['device']
            dst_port = link['dst']['port']
            
            # 存储邻居信息，包括端口
            # 结构: self.adj[src][dst] = {'src_port': p1, 'dst_port': p2}
            self.adj[src_dev][dst_dev] = {
                'src_port': src_port,
                'dst_port': dst_port
            }

    def load_hosts(self, hosts_data):
        """
        从主机数据构建图 (将主机连接到交换机)
        """
        for host in hosts_data:
            host_id = host.get('id')
            locations = host.get('locations', [])
            
            for loc in locations:
                switch_id = loc.get('elementId')
                switch_port = loc.get('port')
                
                # Host -> Switch
                self.adj[host_id][switch_id] = {
                    'src_port': -1, # 主机端端口未知或不重要
                    'dst_port': switch_port
                }
                
                # Switch -> Host
                self.adj[switch_id][host_id] = {
                    'src_port': switch_port,
                    'dst_port': -1
                }

    def get_neighbors(self, device_id):
        """
        获取指定设备的邻居
        """
        return self.adj.get(device_id, {})

    def get_port_to_neighbor(self, src_dev, dst_dev):
        """
        获取从 src 到 dst 的出端口
        """
        if src_dev in self.adj and dst_dev in self.adj[src_dev]:
            return self.adj[src_dev][dst_dev]
        return None

    def find_path(self, start_dev, end_dev):
        """
        使用 BFS 寻找从 start 到 end 的最短路径 (跳数最少)
        返回路径列表: [start, node1, node2, ..., end]
        """
        if start_dev not in self.adj:
            return None
        
        queue = deque([[start_dev]])
        visited = set([start_dev])
        
        while queue:
            path = queue.popleft()
            node = path[-1]
            
            if node == end_dev:
                return path
            
            for neighbor in self.adj.get(node, {}):
                if neighbor not in visited:
                    visited.add(neighbor)
                    new_path = list(path)
                    new_path.append(neighbor)
                    queue.append(new_path)
                    
        return None

    def get_all_devices(self):
        """
        获取图中所有设备 ID
        """
        return list(self.adj.keys())
