package org.example;

import org.onosproject.net.pi.model.DefaultPiPipeconf;
import org.onosproject.net.pi.model.PiPipeconf;
import org.onosproject.net.pi.model.PiPipeconfId;
import org.onosproject.net.pi.service.PiPipeconfService;
import org.onosproject.p4runtime.model.P4InfoParser;
import org.osgi.service.component.annotations.Activate;
import org.osgi.service.component.annotations.Component;
import org.osgi.service.component.annotations.Deactivate;
import org.osgi.service.component.annotations.Reference;
import org.osgi.service.component.annotations.ReferenceCardinality;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URL;

import static org.onosproject.net.pi.model.PiPipeconf.ExtensionType.BMV2_JSON;
import static org.onosproject.net.pi.model.PiPipeconf.ExtensionType.P4_INFO_TEXT;

/**
 * Pipeconf Loader for MyNDP P4 Program.
 */
@Component(immediate = true)
public class PipeconfFactory {

    private static final Logger log = LoggerFactory.getLogger(PipeconfFactory.class);

    // 请确保此 ID 不与 ONOS 现有的 Pipeconf 冲突
    public static final PiPipeconfId PIPECONF_ID = new PiPipeconfId("org.example.myndp");

    // 指向 resources/p4c-out 下的编译产物
    private static final URL BMV2_JSON_URL = PipeconfFactory.class.getResource("/p4c-out/bmv2/bmv2.json");
    private static final URL P4INFO_URL = PipeconfFactory.class.getResource("/p4c-out/bmv2/p4info.txt");

    @Reference(cardinality = ReferenceCardinality.MANDATORY)
    protected PiPipeconfService pipeconfService;

    @Activate
    public void activate() {
        if (BMV2_JSON_URL == null || P4INFO_URL == null) {
            log.warn("P4 artifacts not found! Pipeconf {} cannot be registered.", PIPECONF_ID);
            return;
        }

        try {
            PiPipeconf pipeconf = DefaultPiPipeconf.builder()
                    .withId(PIPECONF_ID)
                    .withPipelineModel(P4InfoParser.parse(P4INFO_URL))
                    .addExtension(P4_INFO_TEXT, P4INFO_URL)
                    .addExtension(BMV2_JSON, BMV2_JSON_URL)
                    // 如果需要自定义 PipelineInterpreter (端口映射/Packet-In处理)，需在此注册
                    // .addBehaviour(PipelineInterpreter.class, MyInterpreter.class)
                    .build();

            pipeconfService.register(pipeconf);
            log.info("Registered Pipeconf: {}", PIPECONF_ID);
        } catch (Exception e) {
            // 捕获所有异常，避免 Bundle 启动失败
            log.error("Failed to register pipeconf: {}", e.getMessage(), e);
        }
    }

    @Deactivate
    public void deactivate() {
        try {
            pipeconfService.unregister(PIPECONF_ID);
            log.info("Unregistered Pipeconf: {}", PIPECONF_ID);
        } catch (Exception e) {
            log.error("Failed to unregister pipeconf: {}", e.getMessage());
        }
    }
}
