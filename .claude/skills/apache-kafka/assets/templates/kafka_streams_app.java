/**
 * Kafka Streams Application Template
 * Replace {{PLACEHOLDERS}} with your values.
 *
 * Dependencies (build.gradle):
 *   implementation 'org.apache.kafka:kafka-streams:3.9.0'
 *   implementation 'io.confluent:kafka-streams-avro-serde:7.7.0'
 */
package {{PACKAGE}};

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.*;
import org.apache.kafka.streams.kstream.*;
import org.apache.kafka.streams.state.KeyValueStore;
import org.apache.kafka.common.utils.Bytes;
import java.time.Duration;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;

public class {{APP_NAME}}StreamsApp {

    public static void main(String[] args) {
        Properties props = new Properties();
        props.put(StreamsConfig.APPLICATION_ID_CONFIG, "{{APP_ID}}");
        props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "{{BOOTSTRAP_SERVERS}}");
        props.put(StreamsConfig.PROCESSING_GUARANTEE_CONFIG, StreamsConfig.EXACTLY_ONCE_V2);
        props.put(StreamsConfig.NUM_STREAM_THREADS_CONFIG, 4);
        props.put(StreamsConfig.COMMIT_INTERVAL_MS_CONFIG, 100);
        props.put(StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG, Serdes.StringSerde.class);
        props.put(StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG, Serdes.StringSerde.class);

        StreamsBuilder builder = new StreamsBuilder();

        // ── Source Stream ──────────────────────────────────────
        KStream<String, String> source = builder.stream("{{INPUT_TOPIC}}");

        // ── Filter + Transform ─────────────────────────────────
        KStream<String, String> filtered = source
            .filter((key, value) -> value != null && !value.isEmpty())
            .mapValues(value -> transform(value));

        // ── Windowed Aggregation (5-minute tumbling) ───────────
        TimeWindows window = TimeWindows.ofSizeWithNoGrace(Duration.ofMinutes(5));
        KTable<Windowed<String>, Long> counts = source
            .groupByKey()
            .windowedBy(window)
            .count(Materialized.<String, Long, KeyValueStore<Bytes, byte[]>>as("{{STORE_NAME}}")
                .withKeySerde(Serdes.String())
                .withValueSerde(Serdes.Long()));

        // ── Output ─────────────────────────────────────────────
        filtered.to("{{OUTPUT_TOPIC}}");
        counts.toStream()
            .map((windowedKey, count) -> KeyValue.pair(windowedKey.key(), count.toString()))
            .to("{{AGGREGATION_TOPIC}}");

        // ── Run ────────────────────────────────────────────────
        KafkaStreams streams = new KafkaStreams(builder.build(), props);
        CountDownLatch latch = new CountDownLatch(1);

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            streams.close(Duration.ofSeconds(30));
            latch.countDown();
        }));

        try {
            streams.start();
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static String transform(String value) {
        // {{TRANSFORM_LOGIC}}
        return value.toUpperCase();
    }
}
