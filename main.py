import onos_api
import json
import sys
from topology_manager import TopologyGraph

appId = "org.onosproject.SDNApp"
flows_template = {
  "priority": 40001,
  "timeout": 0,
  "isPermanent": True,
  "deviceId": "",
  "selector": {
    "criteria": [
      {
        "type": "IN_PORT",
        "port": ""
      }
    ]
  },
  "treatment": {
    "instructions": [
      {
        "type": "OUTPUT",
        "port": ""
      }
    ]
  }
}

import copy

if __name__ == "__main__":
    # 1. 获取拓扑数据
    # 优先从本地文件读取 topo.json，如果不存在则从 API 获取
    try:
        with open('topo.json', 'r') as f:
            print("Loading topology from topo.json...")
            topo = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("topo.json not found or invalid, fetching from api...")
        topo = onos_api.get_links_by_topology_id()
        if topo:
            with open('topo.json', 'w') as f:
                json.dump(topo, f, indent=2)
    
    hosts = onos_api.get_hosts()

    # 2. 初始化图结构
    graph = TopologyGraph(topo, hosts)
    
    # 3. 演示功能
    print(f"Total devices: {len(graph.get_all_devices())}")

    # 显示可用主机
    print("Available Hosts:")
    host_ids = [h['id'] for h in hosts]
    for h_id in host_ids:
        print(f" - {h_id}")
    
    # 等待用户输入
    start_node = input("Please enter the source host ID: ").strip()
    end_node = input("Please enter the destination host ID: ").strip()
    
    path = graph.find_path(start_node, end_node)
    
    if path:
        print(f"Path from {start_node} to {end_node}:")
        print(" -> ".join(path))
        
        print("\nCreating flows for path...")
        # 遍历路径，在中间的交换机上创建流表
        # 路径假设: Host -> Switch -> ... -> Switch -> Host
        # 我们跳过第一个和最后一个节点(主机)，配置中间的交换机
        
        for i in range(1, len(path) - 1):
            prev_node = path[i-1]
            curr_node = path[i]
            next_node = path[i+1]
            
            # 检查当前节点是否为交换机 (简单判断: 以 'of:' 开头)
            if not curr_node.startswith("of:"):
                continue
                
            # 获取入端口 (从 prev_node 到 curr_node 的连接，在 curr_node 上的端口)
            # 我们使用 prev_node -> curr_node 的链路信息中的 dst_port
            port_info_in = graph.get_port_to_neighbor(prev_node, curr_node)
            if not port_info_in:
                print(f"Error: No link from {prev_node} to {curr_node}")
                continue
            in_port = port_info_in['dst_port']
            
            # 获取出端口 (从 curr_node 到 next_node 的连接，在 curr_node 上的端口)
            # 我们使用 curr_node -> next_node 的链路信息中的 src_port
            port_info_out = graph.get_port_to_neighbor(curr_node, next_node)
            if not port_info_out:
                print(f"Error: No link from {curr_node} to {next_node}")
                continue
            out_port = port_info_out['src_port']
            
            print(f"Configuring {curr_node}: IN_PORT={in_port} -> OUTPUT={out_port}")
            
            # 构建流表 (正向)
            flow = copy.deepcopy(flows_template)
            flow["deviceId"] = curr_node
            flow["selector"]["criteria"][0]["port"] = in_port
            flow["treatment"]["instructions"][0]["port"] = out_port
            
            onos_api.create_flow(flow, device_id=curr_node, appId=appId)

            # 构建流表 (反向)
            print(f"Configuring {curr_node} (Return): IN_PORT={out_port} -> OUTPUT={in_port}")
            flow_return = copy.deepcopy(flows_template)
            flow_return["deviceId"] = curr_node
            flow_return["selector"]["criteria"][0]["port"] = out_port
            flow_return["treatment"]["instructions"][0]["port"] = in_port
            
            onos_api.create_flow(flow_return, device_id=curr_node, appId=appId)

    else:
        print(f"No path found from {start_node} to {end_node}")

            