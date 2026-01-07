package org.example;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.onlab.packet.ARP;
import org.onlab.packet.Ethernet;
import org.onlab.packet.Ip4Address;
import org.onlab.packet.MacAddress;
import org.onosproject.core.ApplicationId;
import org.onosproject.core.CoreService;
import org.onosproject.net.DeviceId;
import org.onosproject.net.PortNumber;
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

@Component(immediate = true)
public class AppComponent {

    private final Logger log = LoggerFactory.getLogger(getClass());

    // 依赖注入服务
    @Reference(cardinality = ReferenceCardinality.MANDATORY)
    protected CoreService coreService;

    @Reference(cardinality = ReferenceCardinality.MANDATORY)
    protected PacketService packetService;

    private ApplicationId appId;
    private ArpProcessor processor = new ArpProcessor();

    // 关键点1：独立的线程池处理 HTTP 请求，防止阻塞 Packet 处理线程
    private ExecutorService httpExecutor;
    private HttpClient httpClient;

    // 微服务地址
    private static final String MICROSERVICE_URL = "http://172.21.248.221:5000/api/report/arp";

    @Activate
    protected void activate() {
        appId = coreService.registerApplication("org.example.arp");
        httpExecutor = Executors.newFixedThreadPool(5); // 允许同时发5个请求
        httpClient = HttpClient.newHttpClient();

        // 关键点2：注册处理器，优先级设为 HIGH (2)，确保在 Fwd 模块之前拦截
        packetService.addProcessor(processor, PacketProcessor.director(2));

        // 关键点3：向 OpenFlow 交换机申请拦截 ARP 包
        requestIntercepts();

        log.info("ARP 反应式上报应用已启动");
    }

    @Deactivate
    protected void deactivate() {
        withdrawIntercepts();
        packetService.removeProcessor(processor);
        httpExecutor.shutdown(); // 释放线程池
        log.info("ARP 反应式上报应用已停止");
    }

    // 申请拦截 ARP
    private void requestIntercepts() {
        TrafficSelector.Builder selector = DefaultTrafficSelector.builder();
        selector.matchEthType(Ethernet.TYPE_ARP);
        // 使用 REACTIVE 优先级，告诉 ONOS 这个包很重要
        packetService.requestPackets(selector.build(), PacketPriority.REACTIVE, appId);
    }

    private void withdrawIntercepts() {
        TrafficSelector.Builder selector = DefaultTrafficSelector.builder();
        selector.matchEthType(Ethernet.TYPE_ARP);
        packetService.cancelPackets(selector.build(), PacketPriority.REACTIVE, appId);
    }

    // --- 内部类：包处理器 ---
    private class ArpProcessor implements PacketProcessor {
        @Override
        public void process(PacketContext context) {
            // 如果包已经被处理过，跳过
            if (context.isHandled()) {
                return;
            }

            InboundPacket pkt = context.inPacket();
            Ethernet ethPkt = pkt.parsed();

            // 双重检查：只处理 ARP
            if (ethPkt == null || ethPkt.getEtherType() != Ethernet.TYPE_ARP) {
                return;
            }

            // 解析 ARP 负载
            ARP arp = (ARP) ethPkt.getPayload();

            // 提取关键元数据 (Data Plane Info)
            DeviceId dpid = pkt.receivedFrom().deviceId();
            PortNumber port = pkt.receivedFrom().port();

            // 提取地址信息 (Host Info)
            // 注意：这里要做 try-catch 防止解析异常，这里简化处理
            Ip4Address srcIp = Ip4Address.valueOf(arp.getSenderProtocolAddress());
            MacAddress srcMac = MacAddress.valueOf(arp.getSenderHardwareAddress());
            Ip4Address dstIp = Ip4Address.valueOf(arp.getTargetProtocolAddress());

            log.info("拦截到 ARP: SRC[{}/{}] -> DST[{}] @ {}", srcIp, srcMac, dstIp, dpid);

            // 关键点4：异步提交给 HTTP 线程池
            httpExecutor.execute(() -> sendToMicroservice(dpid, port, srcIp, srcMac, dstIp));

            // 关键点5：阻断泛洪！(Close Broadcast)
            // context.block() 会阻止这个包继续传递给其他 App（如 Fwd），也就不会被 flood
            context.block();
        }
    }

    // --- 辅助方法：发送 HTTP 请求 ---
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

            // 2. 发送请求 (Java 11 HttpClient)
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(MICROSERVICE_URL))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
                    .build();

            // 3. 等待响应（这里是异步线程内，所以可以同步等待）
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 200) {
                log.info("微服务处理成功: " + response.body());
                // 解析响应，查看是否有 Packet-Out 指令
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