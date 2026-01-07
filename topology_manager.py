import json
from collections import defaultdict, deque

class TopologyGraph:
    def __init__(self, links_data=None, hosts_data=None):
        self.adj = defaultdict(dict)
        if links_data:
            self.load_from_data(links_data)
        if hosts_data:
            self.load_hosts(hosts_data)

    def load_from_data(self, links_data):
        self.adj.clear()
        for link in links_data:
            src_dev = link['src']['device']
            src_port = link['src']['port']
            dst_dev = link['dst']['device']
            dst_port = link['dst']['port']
            self.add_link(src_dev, dst_dev, src_port, dst_port)

    def load_hosts(self, hosts_data):
        for host in hosts_data:
            host_id = host.get('id')
            locations = host.get('locations', [])
            for loc in locations:
                switch_id = loc.get('elementId')
                switch_port = loc.get('port')
                self.add_link(host_id, switch_id, -1, switch_port)
                self.add_link(switch_id, host_id, switch_port, -1)

    def add_link(self, src, dst, src_port, dst_port):
        self.adj[src][dst] = {
            'src_port': str(src_port),
            'dst_port': str(dst_port)
        }

    def find_path(self, start, end):
        queue = deque([[start]])
        visited = set([start])
        while queue:
            path = queue.popleft()
            node = path[-1]
            if node == end:
                return path
            for neighbor in self.adj[node]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    new_path = list(path)
                    new_path.append(neighbor)
                    queue.append(new_path)
        return None

    def get_port_to_neighbor(self, current_node, next_node):
        return self.adj[current_node].get(next_node)

    def get_all_devices(self):
        return list(self.adj.keys())
    
    def get_graph_dict(self):
        return {k: v for k, v in self.adj.items()}
