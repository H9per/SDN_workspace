import onos_api


flow_data = {
  "priority": 10,
  "timeout": 0,
  "isPermanent": True,
  "deviceId": "of:0000000000000001",
  "selector": {
    "criteria": [
      {
        "type": "IN_PORT",
        "port": "4"
      }
    ]
  },
  "treatment": {
    "instructions": [
      {
        "type": "OUTPUT",
        "port": "3"
      }
    ]
  }
}

onos_api.create_flow(flow_data,device_id='of:0000000000000001',appId="org.onosproject.emptyId")