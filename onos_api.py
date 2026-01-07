import requests
from requests.auth import HTTPBasicAuth
import json

# ONOS 配置
ONOS_IP = '127.0.0.1'
ONOS_PORT = '8181'
USER = 'karaf'
PASS = 'karaf'
BASE_URL = f'http://{ONOS_IP}:{ONOS_PORT}/onos/v1'

def _get_auth():
    return HTTPBasicAuth(USER, PASS)

def clean_flows(except_id="org.onosproject.core"):
    """
    删除除指定 ID 以外的所有流表。
    :param except_id: 不需要删除的 App ID，默认为 'org.onosproject.core'
    """
    print(f"正在清理流表，保留 App ID: {except_id}...")
    try:
        resp = requests.get(f'{BASE_URL}/flows', auth=_get_auth())
        if resp.status_code != 200:
            print(f"获取流表失败: {resp.status_code} {resp.text}")
            return False
        
        flows = resp.json().get('flows', [])
        apps_to_clean = set()
        for flow in flows:
            app_id = flow.get('appId')
            if app_id and app_id != except_id:
                apps_to_clean.add(app_id)
        if not apps_to_clean:
            print("没有需要清理的流表。")
            return True
        
        for app_id in apps_to_clean:
            print(f"正在删除 App ID 为 {app_id} 的流表 ...")
            del_resp = requests.delete(f'{BASE_URL}/flows/application/{app_id}', auth=_get_auth())
            if del_resp.status_code == 204:
                print(f"  成功删除 {app_id} 的流表")
            else:
                print(f"  删除失败 {app_id}: {del_resp.status_code}")
        
        print("流表清理完成。")
        return True

    except Exception as e:
        print(f"clean_flows 发生错误: {e}")
        return False

def get_flows_by_device_id(device_id=None):
    """
    根据设备 ID 获取流表。如果未提供 device_id，则获取所有流表。
    :param device_id: 设备 ID (例如 'of:0000000000000001')，可选
    :return: 流表列表
    """
    try:
        if device_id:
            url = f'{BASE_URL}/flows/{device_id}'
        else:
            url = f'{BASE_URL}/flows'

        resp = requests.get(url, auth=_get_auth())
        if resp.status_code == 200:
            return resp.json().get('flows', [])
        else:
            target = device_id if device_id else "所有"
            print(f"获取 {target} 流表失败: {resp.status_code}")
            return []
    except Exception as e:
        print(f"get_flows_by_device_id 发生错误: {e}")
        return []

def get_devices_by_topology_id(topology_id=None):
    """
    基于拓扑 ID (Cluster ID) 获取拓扑内的设备列表。
    如果 topology_id 为 None，则获取所有设备。
    :param topology_id: 拓扑集群 ID (例如 '0')
    :return: 设备列表
    """
    try:
        if topology_id is not None:
            url = f'{BASE_URL}/topology/clusters/{topology_id}/devices'
        else:
            url = f'{BASE_URL}/devices'
            
        resp = requests.get(url, auth=_get_auth())
        if resp.status_code == 200:
            return resp.json().get('devices', [])
        else:
            print(f"获取设备列表失败 (topology_id={topology_id}): {resp.status_code}")
            return []
    except Exception as e:
        print(f"get_devices_by_topology_id 发生错误: {e}")
        return []

def get_links_by_topology_id(topology_id=None):
    """
    基于拓扑 ID (Cluster ID) 获取拓扑内的链路。
    如果 topology_id 为 None，则获取所有链路。
    :param topology_id: 拓扑集群 ID (例如 '0')
    :return: 链路列表
    """
    try:
        if topology_id is not None:
            url = f'{BASE_URL}/topology/clusters/{topology_id}/links'
        else:
            url = f'{BASE_URL}/links'
            
        resp = requests.get(url, auth=_get_auth())
        if resp.status_code == 200:
            return resp.json().get('links', [])
        else:
            print(f"获取链路列表失败 (topology_id={topology_id}): {resp.status_code}")
            return []
    except Exception as e:
        print(f"get_links_by_topology_id 发生错误: {e}")
        return []
    
def create_flow(flow_data,device_id=None,appId="org.onosproject.emptyId"):
    """
    在指定设备上创建流表。如果未提供 device_id，则创建全局流表。
    :param flow_data: 流表数据 (字典格式)
    :param device_id: 设备 ID (例如 'of:0000000000000001')，可选
    :return: 创建结果 (True/False)
    """
    try:
        if device_id:
            url = f'{BASE_URL}/flows/{device_id}?appId={appId}'
        else:
            url = f'{BASE_URL}/flows/?appId={appId}'
        
        headers = {'Content-Type': 'application/json'}
        resp = requests.post(url, auth=_get_auth(), headers=headers, data=json.dumps(flow_data))
        if resp.status_code in [200, 201]:
            print(f"流表创建成功 (device_id={device_id})")
            return True
        else:
            print(f"流表创建失败 (device_id={device_id}): {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"create_flow 发生错误: {e}")
        return False
    
def get_hosts():
    """
    获取网络中的所有主机信息。
    :return: 主机列表
    """
    try:
        url = f'{BASE_URL}/hosts'
        resp = requests.get(url, auth=_get_auth())
        if resp.status_code == 200:
            return resp.json().get('hosts', [])
        else:
            print(f"获取主机列表失败: {resp.status_code}")
            return []
    except Exception as e:
        print(f"get_hosts 发生错误: {e}")
        return []
def delete_flow(device_id, flow_id):
    """根据 ID 删除流表"""
    url = f"{BASE_URL}/flows/{device_id}/{flow_id}"
    try:
        response = requests.delete(url)
        if response.status_code == 204:
            print(f"Flow {flow_id} deleted successfully.")
            return True
        else:
            print(f"Failed to delete flow: {response.text}")
            return False
    except Exception as e:
        print(f"Error deleting flow: {e}")
        return False

def send_packet_out(device_id, port, message_type, payload):
    """
    发送 Packet-Out 指令
    注意：ONOS 标准 REST API 的 Packet-Out 比较复杂，通常建议直接通过 POST /onos/v1/packet/out
    但在当前场景下，你的 Java App 已经拦截了包。这里我们其实是希望通知 Python 计算完后，
    Python *告诉* ONOS "请帮我回个包"。
    
    简易实现：向 ONOS 发送一个特定的流表或请求，或者，如果你的 onosapi Java 应用暴露了自定义的 PacketOut 接口，
    这里应该调用那个接口。
    
    假设：Java 端除了接收 /api/report/arp，还暴露了一个 POST /onos/onosapi/packetout (需你自己实现)
    或者，使用 ONOS 原生 API。
    """
    # 模拟实现：打印日志。真正的实现需要 Java 端配合开放 REST 接口，或构造复杂的 OpenFlow 报文
    print(f"Draft: Sending Packet-Out via {device_id}:{port}, Type={message_type}, Payload={payload}")
    pass

def get_flows(device_id):
    """
    为了兼容 api.py 调用，添加 get_flows 别名
    """
    return get_flows_by_device_id(device_id)

def create_flow(flow_json, device_id=None, appId=None):
    """
    创建流表
    :param flow_json: 流表 JSON 结构
    :param device_id: 设备 ID
    :param appId: 应用 ID，如果 flow_json 中未指定，会尝试添加
    """
    if not device_id:
        device_id = flow_json.get('deviceId')
    
    if not device_id:
        print("Error: Device ID required to create flow")
        return False

    if appId:
        flow_json['appId'] = appId
    
    try:
        url = f'{BASE_URL}/flows/{device_id}'
        # onos-api expect appId in query param sometimes but usually in body is enough or both
        params = {'appId': appId} if appId else {}
        resp = requests.post(url, json=flow_json, params=params, auth=_get_auth())
        
        if resp.status_code == 201 or resp.status_code == 200:
            print(f"Flow created on {device_id}")
            return True
        else:
            print(f"Failed to create flow: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"Error creating flow: {e}")
        return False
