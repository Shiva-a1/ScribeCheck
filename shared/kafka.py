import json
import logging
import time

from confluent_kafka import Consumer, KafkaException, Producer
from confluent_kafka.admin import AdminClient, NewTopic

from shared import config

TOPICS = ["sheets", "answers", "evidence", "judgments", "graded", "dead-letter"]
log = logging.getLogger("kafka")
_producer = None


def ensure_topics(partitions=3):
    admin = AdminClient({"bootstrap.servers": config.KAFKA_BOOTSTRAP})
    existing = admin.list_topics(timeout=10).topics
    missing = [NewTopic(t, num_partitions=partitions, replication_factor=1) for t in TOPICS if t not in existing]
    if not missing:
        return
    for future in admin.create_topics(missing).values():
        try:
            future.result()
        except KafkaException as error:
            if "TOPIC_ALREADY_EXISTS" not in str(error):
                raise


def publish(topic, key, value):
    global _producer
    if _producer is None:
        _producer = Producer({"bootstrap.servers": config.KAFKA_BOOTSTRAP, "enable.idempotence": True})
    _producer.produce(topic, key=str(key), value=json.dumps(value))
    _producer.flush(10)


def run(topic, group, handle, every=None, on_tick=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    ensure_topics()
    consumer = Consumer({
        "bootstrap.servers": config.KAFKA_BOOTSTRAP,
        "group.id": group,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([topic])
    log.info("%s listening on %s", group, topic)
    last_tick = time.monotonic()
    while True:
        if on_tick and time.monotonic() - last_tick > every:
            last_tick = time.monotonic()
            try:
                on_tick()
            except Exception:
                log.exception("periodic task failed")
        message = consumer.poll(1.0)
        if message is None:
            continue
        if message.error():
            log.warning(message.error())
            continue
        value = json.loads(message.value())
        for attempt in range(3):
            try:
                handle(value)
                break
            except Exception:
                log.exception("attempt %d failed for %s", attempt + 1, value)
                time.sleep(2 ** attempt)
        else:
            publish("dead-letter", message.key().decode() if message.key() else "", {"topic": topic, "value": value})
        consumer.commit(message, asynchronous=False)
