/*
 * MyNDP P4 Program
 * Based on basic_tunnel.p4 structure.
 */

#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_IPV4 = 0x0800;
const bit<16> TYPE_MYNDP = 0x8899;

/*************************************************************************
 **************** H E A D E R S  *****************************************
 *************************************************************************/

header ethernet_t {
    bit<48> dstAddr;
    bit<48> srcAddr;
    bit<16> etherType;
}

header ipv4_t {
    bit<4>  version;
    bit<4>  ihl;
    bit<8>  diffserv;
    bit<16> totalLen;
    bit<16> identification;
    bit<3>  flags;
    bit<13> fragOffset;
    bit<8>  ttl;
    bit<8>  protocol;
    bit<16> hdrChecksum;
    bit<32> srcAddr;
    bit<32> dstAddr;
}

// 您的自定义 NDP 头部
header myndp_t {
    bit<8>  msg_type; // 1=Probe, 2=Reply
    bit<32> seq_id;
    bit<48> tx_timestamp;
    bit<32> sw_id;
    bit<32> src_port; // Source Port (out port of the sender)
}

// Packet-in/Packet-out metadata (Standard for ONOS)
@controller_header("packet_in")
header packet_in_header_t {
    bit<9> ingress_port;
    bit<7> _pad;
}

@controller_header("packet_out")
header packet_out_header_t {
    bit<9> egress_port;
    bit<7> _pad;
}

struct headers {
    ethernet_t       ethernet;
    ipv4_t           ipv4;
    myndp_t          myndp;
    packet_in_header_t packet_in;
    packet_out_header_t packet_out;
}

struct metadata {
    // 可以在这里添加自定义 metadata
}

/*************************************************************************
 **************** P A R S E R  *******************************************
 *************************************************************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
        transition select(standard_metadata.ingress_port) {
            // 假设 255 是 CPU 端口 (packet-out)
            255: parse_packet_out;
            default: parse_ethernet;
        }
    }
    
    state parse_packet_out {
        packet.extract(hdr.packet_out);
        transition parse_ethernet;
    }

    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            TYPE_IPV4: parse_ipv4;
            TYPE_MYNDP: parse_myndp;
            default: accept;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition accept;
    }

    state parse_myndp {
        packet.extract(hdr.myndp);
        transition accept;
    }
}

/*************************************************************************
 **************** C H E C K S U M  ***************************************
 *************************************************************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply {  }
}

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply {  }
}

/*************************************************************************
 **************** I N G R E S S  *****************************************
 *************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    action drop() {
        mark_to_drop(standard_metadata);
    }

    // 新增：打时间戳 Action
    action add_timestamp() {
        // 使用 ingress_global_timestamp (微秒级，取决于实现)
        hdr.myndp.tx_timestamp = standard_metadata.ingress_global_timestamp;
    }

    // 基本的 L2 转发
    action send_to_port(bit<9> port) {
        standard_metadata.egress_spec = port;
    }
    
    // 发送给控制器 (Packet-In)
    action send_to_cpu() {
        standard_metadata.egress_spec = 255; 
        // 在 Egress 中会处理头部封装
    }

    table t_l2_fwd {
        key = {
            hdr.ethernet.dstAddr: exact;
        }
        actions = {
            send_to_port;
            drop;
            // send_to_cpu; // 也可以作为默认动作或匹配动作
        }
        size = 1024;
        default_action = drop();
    }

    const bit<16> TYPE_IPV4 = 0x0800;
    const bit<16> TYPE_MYNDP = 0x8899;
    const bit<16> TYPE_ARP  = 0x0806;

    // ... (中间代码保持不变) ...

    apply {
        // 1. Packet-Out 处理 (控制器发出的包)
        if (hdr.packet_out.isValid()) {
            if (hdr.myndp.isValid()) {
                 add_timestamp();
            }
            standard_metadata.egress_spec = hdr.packet_out.egress_port;
            hdr.packet_out.setInvalid();
            return;
        }

        // 2. 自定义 NDP 探测包处理
        if (hdr.myndp.isValid()) {
            send_to_cpu();
            return;
        }

        // 3. ARP 处理: 必须上送控制器以触发主机发现和路径流表下发
        if (hdr.ethernet.etherType == TYPE_ARP) {
            send_to_cpu();
            return;
        }

        // 4. 普通 L2 转发 (匹配目的 MAC)
        t_l2_fwd.apply();
    }
}

/*************************************************************************
 **************** E G R E S S  *******************************************
 *************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {

    apply {
        // 如果是 MyNDP 数据包且不是发往控制器，说明是发出的探测包
        // 将当前的出口端口 (Egress Port) 写入 src_port 字段
        if (hdr.myndp.isValid() && standard_metadata.egress_port != 255) {
            hdr.myndp.src_port = (bit<32>)standard_metadata.egress_port;
        }

        // 如果目标是 CPU (端口 255)，添加 Packet-In 头部
        if (standard_metadata.egress_port == 255) {
            hdr.packet_in.setValid();
            hdr.packet_in.ingress_port = standard_metadata.ingress_port;
            hdr.packet_in._pad = 0;
        }
    }
}

/*************************************************************************
 **************** D E P A R S E R  ***************************************
 *************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        // 关键顺序：如果有 Packet-In header，必须放在最前面发给控制器
        packet.emit(hdr.packet_in);
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
        packet.emit(hdr.myndp);
    }
}

/*************************************************************************
 **************** M A I N  ***********************************************
 *************************************************************************/

V1Switch(
MyParser(),
MyVerifyChecksum(),
MyIngress(),
MyEgress(),
MyComputeChecksum(),
MyDeparser()
) main;
