package org.example;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.onlab.packet.ARP;
import org.onlab.packet.Data;
import org.onlab.packet.Ethernet;
import org.onlab.packet.Ip4Address;
import org.onlab.packet.MacAddress;
import org.onosproject.core.ApplicationId;
import org.onosproject.core.CoreService;
import org.onosproject.net.ConnectPoint;
import org.onosproject.net.Device;
import org.onosproject.net.DeviceId;
import org.onosproject.net.PortNumber;
import org.onosproject.net.device.DeviceService;
import org.onosproject.net.flow.DefaultTrafficSelector;
import org.onosproject.net.flow.DefaultTrafficTreatment;
import org.onosproject.net.flow.TrafficSelector;
import org.onosproject.net.flow.TrafficTreatment;
import org.onosproject.net.packet.DefaultOutboundPacket;
import org.onosproject.net.packet.InboundPacket;
import org.onosproject.net.packet.OutboundPacket;
import org.onosproject.net.packet.PacketContext;
import org.onosproject.net.packet.PacketPriority;
import org.onosproject.net.packet.PacketProcessor;
import org.onosproject.net.packet.PacketService;
import org.osgi.service.component.annotations.Activate;
import org.osgi.service.component.annotations.Component;
import org.osgi.service.component.annotations.Deactivate;
import org.osgi.service.component.annotations.Reference;
import org.osgi.service.component.annotations.ReferenceCardinality;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

@Component(immediate = true)
public class AppComponent {

    private final Logger log = LoggerFactory.getLogger(getClass());

    // 依赖注入服务
    @Reference(cardinality = ReferenceCardinality.MANDATORY)
    protected CoreService coreService;

    @Reference(cardinality = ReferenceCardinality.MANDATORY)
    protected PacketService packetService;

    @Reference(cardinality = ReferenceCardinality.MANDATORY)
    protected DeviceService deviceService;

    private ApplicationId appId;
    private ArpProcessor processor = new ArpProcessor();

    // 独立的线程池处理 HTTP 请求
    private ExecutorService httpExecutor;
    private HttpClient httpClient;

    // 定时任务执行器 (用于发送探测包)
    private ScheduledExecutorService probeExecutor;

    // 存储 Hash -> DeviceId 的映射
    private ConcurrentHashMap<Integer, DeviceId> deviceIdMap = new ConcurrentHashMap<>();

    // 微服务地址
    private static final String MICROSERVICE_URL = "http://172.21.248.221:5000/api/report/arp";
    private static final String LATENCY_URL = "http://172.21.248.221:5000/api/latency";

    @Activate
    protected void activate() {
        appId = coreService.registerApplication("org.example.arp");
        httpExecutor = Executors.newFixedThreadPool(5); 
        httpClient = HttpClient.newHttpClient();

        // 初始化探测线程池并启动定时探测任务
        probeExecutor = Executors.newSingleThreadScheduledExecutor();
        // 每 2 秒发送一次全网 Probe探测
        probeExecutor.scheduleAtFixedRate(this::sendProbes, 2, 2, TimeUnit.SECONDS);

        // 注册处理器，优先级 HIGH (2)
        packetService.addProcessor(processor, PacketProcessor.director(2));

        requestIntercepts();
        log.info("ARP 反应式上报 & 自定义 NDP 探测应用已启动");
    }

    @Deactivate
    protected void deactivate() {
        withdrawIntercepts();
        packetService.removeProcessor(processor);
        httpExecutor.shutdown();
        probeExecutor.shutdown();
        log.info("应用已停止");
    }

    // 申请拦截 ARP 和 自定义 NDP
    private void requestIntercepts() {
        TrafficSelector.Builder selector = DefaultTrafficSelector.builder();
        
        // 1. 拦截 ARP
        selector.matchEthType(Ethernet.TYPE_ARP);
        packetService.requestPackets(selector.build(), PacketPriority.REACTIVE, appId);

        // 2. 拦截 MyNDP (0x8899)
        TrafficSelector.Builder ndpSelector = DefaultTrafficSelector.builder();
        ndpSelector.matchEthType(MyNdpParser.TYPE_MY_NDP);
        packetService.requestPackets(ndpSelector.build(), PacketPriority.CONTROL, appId);
    }

    private void withdrawIntercepts() {
        TrafficSelector.Builder selector = DefaultTrafficSelector.builder();
        selector.matchEthType(Ethernet.TYPE_ARP);
        packetService.cancelPackets(selector.build(), PacketPriority.REACTIVE, appId);
        
        TrafficSelector.Builder ndpSelector = DefaultTrafficSelector.builder();
        ndpSelector.matchEthType(MyNdpParser.TYPE_MY_NDP);
        packetService.cancelPackets(ndpSelector.build(), PacketPriority.CONTROL, appId);
    }

    // --- 主动探测逻辑 ---
    private void sendProbes() {
        try {
            // 遍历所有可用设备
            for (Device device : deviceService.getAvailableDevices()) {
                // 记录映射关系
                int swIdHash = device.id().hashCode();
                deviceIdMap.put(swIdHash, device.id());

                // 构造 MyNDP 探测包
                Ethernet eth = new Ethernet();
                eth.setSourceMACAddress(MacAddress.ONOS); // 使用 ONOS 虚拟 MAC
                eth.setDestinationMACAddress(MacAddress.BROADCAST);
                eth.setEtherType(MyNdpParser.TYPE_MY_NDP);

                // 构造 Payload (19 Bytes)
                // | msg_type(1) | seq_id(4) | timestamp(6) | sw_id(4) | src_port(4) |
                byte[] payloadData = new byte[19];
                payloadData[0] = 0x01; // MsgType = Probe
                
                // SeqId
                payloadData[1] = 0; payloadData[2] = 0; payloadData[3] = 0; payloadData[4] = 0;
                
                // Timestamp
                long now = System.currentTimeMillis();
                payloadData[5] = (byte) (now >> 40);
                payloadData[6] = (byte) (now >> 32);
                payloadData[7] = (byte) (now >> 24);
                payloadData[8] = (byte) (now >> 16);
                payloadData[9] = (byte) (now >> 8);
                payloadData[10] = (byte) (now);

                // SwId
                payloadData[11] = (byte)(swIdHash >> 24);
                payloadData[12] = (byte)(swIdHash >> 16);
                payloadData[13] = (byte)(swIdHash >> 8);
                payloadData[14] = (byte)(swIdHash);
                
                // SrcPort: Initial 0
                payloadData[15] = 0;
                payloadData[16] = 0;
                payloadData[17] = 0;
                payloadData[18] = 0;

                eth.setPayload(new Data(payloadData));

                floodPacket(device.id(), eth);
            }
        } catch (Exception e) {
            log.error("发送探测包失败: {}", e.getMessage());
        }
    }

    // 手动实现洪泛 (因为 P4 可能不支持 PortNumber.FLOOD)
    // 并且手动填充 MyNDP Payload 中的 src_port 字段
    private void floodPacket(DeviceId deviceId, Ethernet eth) {
        for (org.onosproject.net.Port p : deviceService.getPorts(deviceId)) {
            PortNumber pn = p.number();
            if (!p.isEnabled() || pn.isLogical() || pn.toLong() < 0) {
                continue;
            }

            // 如果是 MyNDP Probe 包，必须修正 Payload 中的 SrcPort
            // 避免 P4 Egress 没能正确覆写导致端口为 0
            if (eth.getEtherType() == MyNdpParser.TYPE_MY_NDP && eth.getPayload() instanceof Data) {
                Data dataPayload = (Data) eth.getPayload();
                byte[] originalData = dataPayload.getData();
                
                // 进行深拷贝以避免多线程修改同一引用
                byte[] newData = new byte[originalData.length];
                System.arraycopy(originalData, 0, newData, 0, originalData.length);
                
                // 覆盖最后4字节 (src_port)
                // 假设 Payload 至少 19 字节
                if (newData.length >= 19) {
                    long portVal = pn.toLong();
                    newData[15] = (byte) (portVal >> 24);
                    newData[16] = (byte) (portVal >> 16);
                    newData[17] = (byte) (portVal >> 8);
                    newData[18] = (byte) (portVal);
                }
                
                // 为该端口创建一个新的 Ethernet 对象 (共享头部，独立 Payload)
                Ethernet ethCopy =  (Ethernet) eth.clone(); 
                ethCopy.setPayload(new Data(newData));
                
                TrafficTreatment treatment = DefaultTrafficTreatment.builder()
                    .setOutput(pn)
                    .build();
                
                OutboundPacket packet = new DefaultOutboundPacket(
                        deviceId,
                        treatment,
                        ByteBuffer.wrap(ethCopy.serialize())
                );
                packetService.emit(packet);
            } else {
                // 普通处理 (如 ARP Request Flood)
                TrafficTreatment treatment = DefaultTrafficTreatment.builder()
                        .setOutput(pn)
                        .build();
                OutboundPacket packet = new DefaultOutboundPacket(
                        deviceId,
                        treatment,
                        ByteBuffer.wrap(eth.serialize())
                );
                packetService.emit(packet);
            }
        }
    }

    // --- 包处理器 ---
    private class ArpProcessor implements PacketProcessor {
        @Override
        public void process(PacketContext context) {
            if (context.isHandled()) return;

            InboundPacket pkt = context.inPacket();
            Ethernet ethPkt = pkt.parsed();
            if (ethPkt == null) return;

            // 分发处理逻辑
            if (ethPkt.getEtherType() == Ethernet.TYPE_ARP) {
                processArp(context, ethPkt);
            } else if (ethPkt.getEtherType() == MyNdpParser.TYPE_MY_NDP) {
                processNdp(context, ethPkt);
            }
        }

        // 处理自定义 NDP 包 (测量时延)
        private void processNdp(PacketContext context, Ethernet ethPkt) {
            DeviceService ds = deviceService; // 使用局部引用或类成员
            
            // 1. 获取接收端口信息
            ConnectPoint cp = context.inPacket().receivedFrom();
            DeviceId rxDeviceId = cp.deviceId();

            // 2. 提取 Payload
            // 注意：Ethernet.getPayload() 可能返回 IPacket 或 Data，这里假设是 Data
            // 如果 P4 解析器正确工作但 ONOS 没有对应 Parser，Payload 通常是 Data 类型
            if (!(ethPkt.getPayload() instanceof Data)) {
                return; // 未知结构
            }
            byte[] rawData = ((Data) ethPkt.getPayload()).getData();

            // 3. 解析 P4 打入的发送时间戳 (Tx Time)
            long txTimestamp = MyNdpParser.extractTimestamp(rawData);
            
            // 4. 获取当前系统时间 (Rx Time)
            // 统一使用 Milliseconds 以匹配 TxTimestamp
            long currentTimestamp = System.currentTimeMillis();

            // 5. 计算往返时延 (RTT)
            // TxTimestamp 是发送时的 System.currentTimeMillis()
            // currentTimestamp 是接收时的 System.currentTimeMillis()
            // 结果单位: 毫秒 (ms)
            long latency = (currentTimestamp > txTimestamp) ? (currentTimestamp - txTimestamp) : 0;
            
            byte msgType = MyNdpParser.extractMsgType(rawData);
            int srcSwIdHash = MyNdpParser.extractSwId(rawData); 
            int srcPortNum = MyNdpParser.extractSrcPort(rawData); // 获取源端口
            
            if (msgType == 1) { // Probe
                String srcDeviceId = "unknown";
                if (deviceIdMap.containsKey(srcSwIdHash)) {
                    srcDeviceId = deviceIdMap.get(srcSwIdHash).toString();
                }
                
                // 注意: srcPortNum 是发送者的 Egress Port
                // rxDeviceId 是接收者 ID, cp.port() 是接收者的 Ingress Port

                log.info("Probe: {}[{}] -> {}[{}] Latency={}ms", 
                       srcDeviceId, srcPortNum, rxDeviceId, cp.port(), latency);
                
                // 上报数据
                String finalSrcDeviceId = srcDeviceId;
                int finalSrcPort = srcPortNum;
                httpExecutor.execute(new Runnable() {
                    @Override
                    public void run() {
                        sendLatencyReport(finalSrcDeviceId, finalSrcPort, rxDeviceId.toString(), cp.port().toLong(), latency);
                    }
                });
            }

            // 阻止继续传播
            context.block();
        }

        private void processArp(PacketContext context, Ethernet ethPkt) {
            InboundPacket pkt = context.inPacket();
            ARP arp = (ARP) ethPkt.getPayload();
            DeviceId dpid = pkt.receivedFrom().deviceId();
            PortNumber port = pkt.receivedFrom().port();

            Ip4Address srcIp = Ip4Address.valueOf(arp.getSenderProtocolAddress());
            MacAddress srcMac = MacAddress.valueOf(arp.getSenderHardwareAddress());
            Ip4Address dstIp = Ip4Address.valueOf(arp.getTargetProtocolAddress());

            log.info("ARP: SRC[{}/{}] -> DST[{}] @ {}", srcIp, srcMac, dstIp, dpid);

            httpExecutor.execute(new Runnable() {
                @Override
                public void run() {
                    sendToMicroservice(dpid, port, srcIp, srcMac, dstIp);
                }
            });
            context.block();
        }
    }

    private void sendLatencyReport(String srcDeviceId, int srcPort, String dstDeviceId, long dstPort, long latencyMs) {
        try {
            ObjectMapper mapper = new ObjectMapper();
            ObjectNode json = mapper.createObjectNode();
            json.put("type", "latency_report");
            json.put("src_device", srcDeviceId); 
            json.put("src_port", String.valueOf(srcPort));
            json.put("dst_device", dstDeviceId);
            json.put("dst_port", String.valueOf(dstPort));
            json.put("latency_ms", latencyMs);
            json.put("timestamp", System.currentTimeMillis());

            String jsonBody = json.toString();

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(LATENCY_URL))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
                    .build();

            httpClient.sendAsync(request, HttpResponse.BodyHandlers.discarding());
        
        } catch (Exception e) {
            log.error("上报时延数据失败: " + e.getMessage());
        }
    }

    private void sendToMicroservice(DeviceId dpid, PortNumber port, Ip4Address srcIp, MacAddress srcMac, Ip4Address dstIp) {
        try {
            // 1. 构建 JSON
            ObjectMapper mapper = new ObjectMapper();
            ObjectNode json = mapper.createObjectNode();
            json.put("dpid", dpid.toString());
            json.put("port", port.toString());
            json.put("src_ip", srcIp.toString());
            json.put("src_mac", srcMac.toString());
            json.put("dst_ip", dstIp.toString());

            String jsonBody = json.toString();

            // 2. 发送请求
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(MICROSERVICE_URL))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 200) {
                log.info("微服务处理成功: " + response.body());
                JsonNode responseJson = mapper.readTree(response.body());
                if (responseJson.has("action") && "packet-out".equals(responseJson.get("action").asText())) {
                    handlePacketOutInstruction(responseJson.get("payload"));
                }
            } else {
                log.warn("微服务返回错误: " + response.statusCode());
            }

        } catch (Exception e) {
            log.error("上报微服务失败: " + e.getMessage());
        }
    }

    private void handlePacketOutInstruction(JsonNode payload) {
        try {
            DeviceId dpid = DeviceId.deviceId(payload.get("dpid").asText());
            PortNumber port = PortNumber.portNumber(payload.get("port").asText());
            String type = payload.get("type").asText();

            if ("ARP_REPLY".equals(type)) {
                MacAddress srcMac = MacAddress.valueOf(payload.get("src_mac").asText());
                Ip4Address srcIp = Ip4Address.valueOf(payload.get("src_ip").asText());
                MacAddress dstMac = MacAddress.valueOf(payload.get("dst_mac").asText());
                Ip4Address dstIp = Ip4Address.valueOf(payload.get("dst_ip").asText());

                // 构造 ARP Reply
                Ethernet ethReply = new Ethernet();
                ethReply.setSourceMACAddress(srcMac);
                ethReply.setDestinationMACAddress(dstMac);
                ethReply.setEtherType(Ethernet.TYPE_ARP);

                ARP arpReply = new ARP();
                arpReply.setOpCode(ARP.OP_REPLY);
                arpReply.setProtocolType(ARP.PROTO_TYPE_IP);
                arpReply.setHardwareType(ARP.HW_TYPE_ETHERNET);
                arpReply.setProtocolAddressLength((byte) 4);
                arpReply.setHardwareAddressLength((byte) 6);
                arpReply.setSenderHardwareAddress(srcMac.toBytes());
                arpReply.setSenderProtocolAddress(srcIp.toOctets());
                arpReply.setTargetHardwareAddress(dstMac.toBytes());
                arpReply.setTargetProtocolAddress(dstIp.toOctets());

                ethReply.setPayload(arpReply);

                emitPacket(dpid, port, ethReply);
            } else if ("ARP_REQUEST".equals(type)) {
                // 洪泛原始 ARP Request 以发现主机
                MacAddress srcMac = MacAddress.valueOf(payload.get("src_mac").asText());
                Ip4Address srcIp = Ip4Address.valueOf(payload.get("src_ip").asText());
                // dstMac 对于 Request 应该是 00:00... 或忽略，广播目的是 FF:FF...
                // payload.get("dst_ip") 是目标IP
                Ip4Address dstIp = Ip4Address.valueOf(payload.get("dst_ip").asText());

                Ethernet ethReq = new Ethernet();
                ethReq.setSourceMACAddress(srcMac);
                ethReq.setDestinationMACAddress(MacAddress.BROADCAST);
                ethReq.setEtherType(Ethernet.TYPE_ARP);

                ARP arpReq = new ARP();
                arpReq.setOpCode(ARP.OP_REQUEST);
                arpReq.setProtocolType(ARP.PROTO_TYPE_IP);
                arpReq.setHardwareType(ARP.HW_TYPE_ETHERNET);
                arpReq.setProtocolAddressLength((byte) 4);
                arpReq.setHardwareAddressLength((byte) 6);
                arpReq.setSenderHardwareAddress(srcMac.toBytes());
                arpReq.setSenderProtocolAddress(srcIp.toOctets());
                arpReq.setTargetHardwareAddress(MacAddress.ZERO.toBytes());
                arpReq.setTargetProtocolAddress(dstIp.toOctets());

                ethReq.setPayload(arpReq);

                // Flood using manual iteration
                floodPacket(dpid, ethReq);
                log.info("已洪泛 ARP Request: {} -> {} @ {}", srcIp, dstIp, dpid);
            }
        } catch (Exception e) {
            log.error("Packet-Out 执行失败: " + e.getMessage());
        }
    }

    private void emitPacket(DeviceId dpid, PortNumber port, Ethernet eth) {
        TrafficTreatment treatment = DefaultTrafficTreatment.builder().setOutput(port).build();
        OutboundPacket packet = new DefaultOutboundPacket(dpid, treatment, ByteBuffer.wrap(eth.serialize()));
        packetService.emit(packet);
        log.info("已发送 Packet-Out 到: {}/{}", dpid, port);
    }
}