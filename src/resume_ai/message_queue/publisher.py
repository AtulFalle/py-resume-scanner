import json
import logging

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractChannel, AbstractRobustConnection

from resume_ai.core.config import settings

logger = logging.getLogger(__name__)

DEAD_LETTER_EXCHANGE = "resume.dlx"
DEAD_LETTER_QUEUE = "resume.dlq"


class RabbitMQPublisher:
    QUEUE_NAME = "resume.processing"

    def __init__(self) -> None:
        self.connection: AbstractRobustConnection | None = None
        self.channel: AbstractChannel | None = None
        self._declared: set[str] = set()

    async def connect(self) -> None:
        self.connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        self.channel = await self.connection.channel(publisher_confirms=True)
        self._declared.clear()

        await self.declare_queue(self.QUEUE_NAME)

        logger.info("RabbitMQ publisher connected")

    async def declare_queue(self, queue_name: str) -> None:
        """Declare a durable queue whose rejected messages go to resume.dlq."""
        if self.channel is None:
            raise RuntimeError("RabbitMQ publisher is not connected")

        if queue_name in self._declared:
            return

        dead_letter_exchange = await self.channel.declare_exchange(
            DEAD_LETTER_EXCHANGE,
            ExchangeType.DIRECT,
            durable=True,
        )
        dead_letter_queue = await self.channel.declare_queue(DEAD_LETTER_QUEUE, durable=True)
        await dead_letter_queue.bind(dead_letter_exchange, routing_key=queue_name)

        await self.channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
                "x-dead-letter-routing-key": queue_name,
            },
        )

        self._declared.add(queue_name)

    async def publish_message(self, queue_name: str, payload: dict) -> None:
        if self.channel is None or self.channel.is_closed:
            raise RuntimeError("RabbitMQ publisher is not connected")

        await self.declare_queue(queue_name)

        message = Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
        )

        await self.channel.default_exchange.publish(message, routing_key=queue_name)

        logger.info("Published message to %s", queue_name)

    async def publish_resume(self, resume_id: str, object_name: str) -> None:
        await self.publish_message(
            self.QUEUE_NAME,
            {"resume_id": resume_id, "object_name": object_name},
        )

    async def close(self) -> None:
        if self.connection and not self.connection.is_closed:
            await self.connection.close()


publisher = RabbitMQPublisher()
