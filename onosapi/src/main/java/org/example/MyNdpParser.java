package org.example;

/**
 * Utility class for parsing MyNDP protocol headers.
 * <p>
 * MyNDP Header Structure (Now 19 Bytes):
 * | msg_type(1B) | seq_id(4B) | timestamp(6B) | sw_id(4B) | src_port(4B) |
 */
public class MyNdpParser {

    public static final short TYPE_MY_NDP = (short) 0x8899;

    /**
     * Extracts the 48-bit timestamp from the payload.
     * The timestamp is located at byte offset 5 (0-indexed).
     *
     * @param payload The raw payload data (excluding Ethernet Header).
     * @return The 48-bit timestamp as a long value, or 0 if payload is too short.
     */
    public static long extractTimestamp(byte[] payload) {
        // Validation: payload must have at least 11 bytes (1 + 4 + 6) to contain the timestamp
        if (payload == null || payload.length < 11) {
            return 0;
        }

        // Timestamp starts at index 5 (after msg_type[1] + seq_id[4])
        int offset = 5;
        long timestamp = 0;

        // Read 6 bytes (48 bits) in Big-Endian order
        for (int i = 0; i < 6; i++) {
            timestamp = (timestamp << 8) | (payload[offset + i] & 0xFF);
        }

        return timestamp;
    }

    /**
     * Extracts the message type from the payload.
     * @param payload The raw payload data.
     * @return The message type (e.g., 1=Probe, 2=Reply), or 0 on error.
     */
    public static byte extractMsgType(byte[] payload) {
        if (payload == null || payload.length < 1) {
            return 0;
        }
        return payload[0];
    }

    public static int extractSwId(byte[] payload) {
        if (payload == null || payload.length < 15) return 0;
        int swId = 0;
        swId |= (payload[11] & 0xFF) << 24;
        swId |= (payload[12] & 0xFF) << 16;
        swId |= (payload[13] & 0xFF) << 8;
        swId |= (payload[14] & 0xFF);
        return swId;
    }

    public static int extractSrcPort(byte[] payload) {
        // Must have at least 19 bytes (msg_type + seq + ts + sw + port)
        if (payload == null || payload.length < 19) return 0;
        int port = 0;
        port |= (payload[15] & 0xFF) << 24;
        port |= (payload[16] & 0xFF) << 16;
        port |= (payload[17] & 0xFF) << 8;
        port |= (payload[18] & 0xFF);
        return port;
    }
}
