from flask import Flask, request, jsonify, render_template
import logging
import threading
import time
import copy
import onos_api
from topology_manager import TopologyGraph

app = Flask(__name__)

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

APP_ID = "org.example.onosapi"
global_graph = TopologyGraph()
link_stats = {}
host_ip_map = {}

flows_template = {
  "priority": 40001,
  "timeout": 0,
  "isPermanent": True,
  "deviceId": "",
  "selector": {"criteria": [{"type": "IN_PORT", "port": ""}, {"type": "ETH_DST", "mac": ""}]},
  "treatment": {"instructions": [{"type": "OUTPUT", "port": ""}]}
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/topology', methods=['GET'])
def get_topology():
    nodes = set()
    processed_pairs = set() 
    links = []
    
    adj = global_graph.get_graph_dict()
    for src, neighbors in adj.items():
        nodes.add(src)
        for dst, ports in neighbors.items():
            nodes.add(dst)
            
            pair_key = tuple(sorted((src, dst)))
            if pair_key in processed_pairs:
                continue
            processed_pairs.add(pair_key)
            
            key_fwd = f"{src}->{dst}"
            lat_fwd = link_stats.get(key_fwd, {}).get("latency", 0)
            
            key_rev = f"{dst}->{src}"
            lat_rev = link_stats.get(key_rev, {}).get("latency", 0)

            val_fwd = round(float(lat_fwd), 1)
            val_rev = round(float(lat_rev), 1)

            links.append({
                "source": pair_key[0],
                "target": pair_key[1],
                "latency_fwd": val_fwd if f"{pair_key[0]}->{pair_key[1]}" == key_fwd else val_rev,
                "latency_rev": val_rev if f"{pair_key[0]}->{pair_key[1]}" == key_fwd else val_fwd,
                "src_port": ports['src_port'],
                "dst_port": ports['dst_port']
            })
            
    node_list = [{"id": n, "group": 1 if n.startswith("of:") else 2} for n in list(nodes)]
    return jsonify({"nodes": node_list, "links": links})

@app.route('/api/latency', methods=['POST'])
def handle_latency():
    data = request.json
    src = data.get('src_device')
    src_port = data.get('src_port', '?')
    dst = data.get('dst_device')
    dst_port = data.get('dst_port', '?')
    ts = data.get('timestamp')
    
    if 'latency_ms' in data:
        latency = data.get('latency_ms')
    else:
        latency = data.get('latency_us', 0) / 1000.0
    
    if src == "unknown":
        logger.warning(f"Ignored report with unknown source -> {dst}")
        return jsonify({"status": "ignored"}), 200

    if str(src_port) == '?' or str(dst_port) == '?':
         logger.warning(f"Ignored link with invalid port: {src}:{src_port} -> {dst}:{dst_port}")
         return jsonify({"status": "ignored_invalid_port"}), 200

    global_graph.add_link(src, dst, src_port, dst_port)
    
    key = f"{src}->{dst}"
    link_stats[key] = {"latency": latency, "timestamp": ts}
    
    return jsonify({"status": "ok"})

@app.route('/api/report/arp', methods=['POST'])
def report_arp():
    try:
        data = request.json
        dpid = data.get('dpid')
        port = data.get('port')
        src_mac = data.get('src_mac') 
        src_ip = data.get('src_ip')
        dst_ip = data.get('dst_ip')
        
        if src_ip and src_mac:
            host_ip_map[src_ip] = {
                "mac": src_mac,
                "dpid": dpid,
                "port": port
            }
            logger.info(f"Host Discovered: {src_ip} -> {src_mac} @ {dpid}/{port}")
        
        src_host_id = f"{src_mac}/None" 
        global_graph.add_link(src_host_id, dpid, -1, port)
        global_graph.add_link(dpid, src_host_id, port, -1)
        
        if dst_ip in host_ip_map:
            dst_info = host_ip_map[dst_ip]
            dst_mac = dst_info['mac']
            
            logger.info(f"Target {dst_ip} found! Preparing ARP Reply and Flows...")
            
            install_path_flows(src_host_id, f"{dst_mac}/None", src_ip, dst_ip)
            
            reply_instruction = {
                "type": "ARP_REPLY",
                "src_mac": dst_mac,
                "src_ip": dst_ip,
                "dst_mac": src_mac,
                "dst_ip": src_ip,
                "dpid": dpid,
                "port": port
            }
            
            return jsonify({
                "status": "processed",
                "action": "packet-out",
                "payload": reply_instruction
            }), 200
            
        else:
            logger.info(f"Target {dst_ip} unknown. Waiting for discovery.")
            return jsonify({"status": "received"}), 200
        
    except Exception as e:
        logger.error(f"ARP Error: {e}")
        return jsonify({"status": "error"}), 500

def install_path_flows(src_id, dst_id, src_ip, dst_ip):
    path = global_graph.find_path(src_id, dst_id)
    if not path:
        logger.error("No path found between hosts!")
        return

    logger.info(f"Path Calculation: {path}")
    
    onos_api.clean_flows(except_id="org.onosproject.core")
    
    src_info = host_ip_map[src_ip]
    dst_info = host_ip_map[dst_ip]
    
    for i in range(1, len(path) - 1):
        curr_sw = path[i]
        prev_node = path[i-1]
        next_node = path[i+1]
        
        if curr_sw not in global_graph.adj or prev_node not in global_graph.adj[curr_sw] or next_node not in global_graph.adj[curr_sw]:
             logger.error(f"Link missing in AJD for {prev_node}-{curr_sw}-{next_node}")
             continue
             
        port_to_prev = global_graph.adj[curr_sw][prev_node]['src_port']
        
        port_to_next = global_graph.adj[curr_sw][next_node]['src_port']

        if str(port_to_prev) == '?' or str(port_to_next) == '?':
            logger.error(f"Cannot install flow on {curr_sw}: Invalid port detected. PrevPort={port_to_prev}, NextPort={port_to_next}")
            continue

        logger.info(f"Installing Flow on {curr_sw}: to_prev={port_to_prev}, to_next={port_to_next}")
        
        flow_fwd = copy.deepcopy(flows_template)
        flow_fwd['deviceId'] = curr_sw
        flow_fwd['selector']['criteria'] = [
            {"type": "ETH_DST", "mac": dst_info['mac']}
        ]
        flow_fwd['treatment']['instructions'] = [
            {"type": "OUTPUT", "port": port_to_next}
        ]
        onos_api.create_flow(flow_fwd, curr_sw, APP_ID)
        
        flow_rev = copy.deepcopy(flows_template)
        flow_rev['deviceId'] = curr_sw
        flow_rev['selector']['criteria'] = [
            {"type": "ETH_DST", "mac": src_info['mac']}
        ]
        flow_rev['treatment']['instructions'] = [
            {"type": "OUTPUT", "port": port_to_prev}
        ]
        onos_api.create_flow(flow_rev, curr_sw, APP_ID)

if __name__ == '__main__':
    logger.info("Starting Topology Service on :5000")
    app.run(host='0.0.0.0', port=5000)
