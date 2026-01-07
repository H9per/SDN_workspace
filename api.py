from flask import Flask, request, jsonify
import logging
import threading
import time
import copy
import onos_api
from topology_manager import TopologyGraph

app = Flask(__name__)

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# 全局拓扑对象
global_graph = None
APP_ID = "org.example.arp"

# 流表模板
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
      },
      {
        "type": "ETH_DST",
        "mac": ""
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

def update_topology_task():
    """每 5 秒更新一次拓扑"""
    global global_graph
    while True:
        try:
            logger.info("正在更新网络拓扑...")
            links = onos_api.get_links_by_topology_id()
            hosts = onos_api.get_hosts()
            global_graph = TopologyGraph(links, hosts)
            logger.info(f"拓扑更新完成: {len(global_graph.get_all_devices())} devices, {len(hosts)} hosts")
            
        except Exception as e:
            logger.error(f"拓扑更新失败: {e}")
        
        time.sleep(5)

def cleanup_conflicting_flows(device_id, match_criteria):
    try:
        flows = onos_api.get_flows(device_id)
        if not flows:
            return

        target_eth_dst = match_criteria.get("ETH_DST")
        target_in_port = match_criteria.get("IN_PORT")

        for flow in flows:
            flow_app_id = flow.get("appId")
            if flow_app_id != APP_ID:
                continue

            criteria_list = flow.get("selector", {}).get("criteria", [])
            
            # ONOS criteria 示例: {"type": "ETH_DST", "mac": "..."}
            criteria_map = {c.get("type"): c for c in criteria_list}

            existing_mac = criteria_map.get("ETH_DST", {}).get("mac")

            if existing_mac and existing_mac.upper() == target_eth_dst.upper():
                logger.info(f"清理旧流表: dev={device_id}, flowId={flow.get('id')}, mac={existing_mac}")
                onos_api.delete_flow(device_id, flow.get('id'))
                time.sleep(0.1) 
            
    except Exception as e:
        logger.warning(f"清理流表异常: {e}")

def install_path_flows(src_host_id, dst_host_id, src_mac, dst_mac):
    if not global_graph:
        logger.warning("拓扑尚未就绪")
        return False
    path = global_graph.find_path(src_host_id, dst_host_id)
    if not path:
        logger.warning(f"找不到路径: {src_host_id} -> {dst_host_id}")
        return False
    for i in range(1, len(path) - 1):
        prev_node = path[i-1]
        curr_node = path[i]
        next_node = path[i+1]
        if not curr_node.startswith("of:"):
            continue
        link_in = global_graph.get_port_to_neighbor(prev_node, curr_node)
        link_out = global_graph.get_port_to_neighbor(curr_node, next_node)
        if not link_in or not link_out:
            logger.error(f"链路缺失: {prev_node}-{curr_node}-{next_node}")
            return False
        in_port = link_in['dst_port']
        out_port = link_out['src_port']
        install_flow_rule(curr_node, in_port, out_port, dst_mac)
        install_flow_rule(curr_node, out_port, in_port, src_mac)

    return True

def install_flow_rule(device_id, in_port, out_port, match_dst_mac):
    match_criteria = {
        "ETH_DST": match_dst_mac,
        "IN_PORT": in_port
    }
    cleanup_conflicting_flows(device_id, match_criteria)
    
    # 3. 构造新流表
    flow = copy.deepcopy(flows_template)
    flow["deviceId"] = device_id
    # 入端口
    flow["selector"]["criteria"][0]["port"] = in_port
    # 目的MAC
    flow["selector"]["criteria"][1]["mac"] = match_dst_mac
    # 从出端口转发
    flow["treatment"]["instructions"][0]["port"] = out_port
    
    logger.info(f"下发流表: Dev={device_id} Match=[In:{in_port}, Dst:{match_dst_mac}] -> Out:{out_port}")
    onos_api.create_flow(flow, device_id, appId=APP_ID)

@app.route('/api/report/arp', methods=['POST'])
def report_arp():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No JSON data"}), 400
        dpid = data.get('dpid')
        port = data.get('port')
        src_ip = data.get('src_ip')
        src_mac = data.get('src_mac')
        dst_ip = data.get('dst_ip')
        logger.info(f"收到 ARP 上报: SRC[{src_ip}/{src_mac}] -> DST[{dst_ip}] @ {dpid}:{port}")
        target_host = None
        target_mac = None
        if global_graph:
            hosts = onos_api.get_hosts()
            for h in hosts:
                if dst_ip in h.get('ipAddresses', []):
                    target_host = h['id']
                    target_mac = h['mac']
                    break
        
        if target_host:
            src_host_id = f"{src_mac}/None" 
            success = install_path_flows(src_host_id, target_host, src_mac, target_mac) # src_host_id is guessed
            
            if success:
                #代答 ARP 
                response_payload = {
                    "action": "packet-out",
                    "payload": {
                        "type": "ARP_REPLY",
                        "dpid": dpid,
                        "port": port,
                        "src_mac": target_mac, # 目标主机
                        "src_ip": dst_ip,
                        "dst_mac": src_mac,    # 请求者
                        "dst_ip": src_ip
                    }
                }
                return jsonify(response_payload), 200
            else:
                logger.warning("路径安装失败，无法代答")
        else:
            logger.info("目标主机未知，无法处理 (等待目标主机发包)")
            # 此时无法做任何事，从网络视角看，ARP 会超时
        
        return jsonify({"status": "success", "message": "No path or host found"}), 200
        
    except Exception as e:
        logger.error(f"处理异常: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    topo_thread = threading.Thread(target=update_topology_task, daemon=True)
    topo_thread.start()
    
    logger.info("启动 ARP 监听微服务 (Port 5000)...")
    app.run(host='0.0.0.0', port=5000)
