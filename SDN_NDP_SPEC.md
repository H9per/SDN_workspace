# SDN_NDP 协议规范

本文档定义了自定义邻居发现协议 (SDN_NDP) 的报文格式与处理规范，用于 SDN 网络中的链路发现与时延测量。

## 1. 协议概述

SDN_NDP 运行在 Ethernet 层之上，通过自定义 EtherType 标识。主要用于控制器主动探测交换机之间的链路连接关系及链路性能。

## 2. 报文封装

### 2.1 Ethernet Header

标准以太网头部：

| 字段 | 长度 | 值 | 说明 |
| :--- | :--- | :--- | :--- |
| Destination MAC | 6 Bytes | `ff:ff:ff:ff:ff:ff` (广播) 或 特定MAC | 探测时通常为广播 |
| Source MAC | 6 Bytes | 发送接口 MAC | |
| **EtherType** | **2 Bytes** | **`0x8899`** | **自定义 SDN_NDP 协议类型** |

### 2.2 MyNDP Header

紧接在 Ethernet Header 之后：

| 字段名 | 长度 (Bit) | 长度 (Byte) | 类型 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| **msg_type** | 8 | 1 | uint8 | 报文类型。<br> `1` = **Probe** (探测请求)<br> `2` = **Reply** (探测回复/上报) |
| **seq_id** | 32 | 4 | uint32 | 序列号，用于匹配请求与响应，或检测丢包。 |
| **tx_timestamp**| 48 | 6 | uint48 | 发送时间戳。通常使用微秒或纳秒精度 (参考 BMv2 标准时间戳宽度)。 |
| **sw_id** | 32 | 4 | uint32 | 发送该报文的交换机 ID (Datapath ID 的低32位或自定义索引)。 |

**Header 总长度**: 1 + 4 + 6 + 4 = **15 Bytes**

## 3. 字段详解

### msg_type
*   `0x01` (Probe): 由控制器构造 Packet-Out 发出，或由交换机周期性发出，用于发现链路邻居。
*   `0x02` (Reply): 交换机收到 Probe 后上报给控制器（Packet-In），或者作为回包发送。

### seq_id
*   由控制器或发送端生成。
*   每次发送探测报文时递增。
*   用于计算丢包率和匹配 RTT 测量。

### tx_timestamp
*   48位时间戳。
*   **用途**: 计算链路单向时延或 RTT。
*   **格式**: 建议使用 UNIX 时间戳（微秒）或交换机本地时钟值。

### sw_id
*   标识该探测报文的源头交换机。
*   当邻居交换机收到此报文时，可以通过读取 `sw_id` 知道自己连接的是哪台交换机。

## 4. 交互流程 (示例)

1.  **控制器发送探测**:
    *   控制器封装 Ethernet(`0x8899`) + MyNDP(`msg_type=1`, `sw_id=SwA`, `ts=T1`)。
    *   通过 Packet-Out 指令指示 Switch A 从所有端口发出。

2.  **交换机转发/接收**:
    *   Switch B 收到该报文。
    *   根据流表规则（匹配 `EthType=0x8899`），将报文封装进 Packet-In 发送给控制器。

3.  **控制器处理**:
    *   控制器解析 Packet-In。
    *   提取 payload 中的 MyNDP Header。
    *   得知: Switch B 的某个端口 连接到了 Switch A (`sw_id`)。
    *   记录链路关系：`A -> B`。
    *   计算时延：`CurrentTime - tx_timestamp`。
