import json

import aio_pika
from aio_pika import DeliveryMode, Message

from resume_ai.core.config import settings
from aio_pika import ExchangeType


DEAD_LETTER_EXCHANGE = "resume.dlx"

class RabbitMQPublisher:
    QUEUE_NAME = "resume.processing"


    def __init__(self) -> None:
        self.connection = None
        self.channel = None

    async def connect(self) -> None:
        self.connection = await aio_pika.connect_robust(settings.rabbitmq_url)

        self.channel = await self.connection.channel(publisher_confirms=True)

        from aio_pika import ExchangeType

        # Inside connect(), after creating the channel:

        await self.channel.declare_exchange(
            "resume.dlx",
            ExchangeType.DIRECT,
            durable=True,
        )

        await self.channel.declare_queue(
            "resume.dlq",
            durable=True,
        )

        await self.channel.declare_queue(
            self.QUEUE_NAME,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "resume.dlx",
                "x-dead-letter-routing-key": self.QUEUE_NAME,
            },
        )

    async def publish_resume(
        self,
        resume_id: str,
        object_name: str,
    ) -> None:
        if self.channel is None:
            raise RuntimeError("RabbitMQ publisher is not connected")

        message = Message(
            body=json.dumps(
                {
                    "resume_id": resume_id,
                    "object_name": object_name,
                }
            ).encode(),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=resume_id,
        )

        await self.channel.default_exchange.publish(
            message,
            routing_key=self.QUEUE_NAME,
        )

    async def close(self) -> None:
        if self.connection and not self.connection.is_closed:
            await self.connection.close()

    async def publish_message(
        self,
        queue_name: str,
        payload: dict,
    ) -> None:
        if self.channel is None:
            raise RuntimeError("RabbitMQ publisher is not connected")

        await self.declare_queue(queue_name)

        message = Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
        )

        await self.channel.default_exchange.publish(
            message,
            routing_key=queue_name,
        )

    async def declare_queue(self, queue_name: str):
        if self.channel is None:
            raise RuntimeError("RabbitMQ publisher is not connected")

        dlx = await self.channel.declare_exchange(
            DEAD_LETTER_EXCHANGE,
            ExchangeType.DIRECT,
            durable=True,
        )

        queue = await self.channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
                "x-dead-letter-routing-key": queue_name,
            },
        )

        dlq = await self.channel.declare_queue(
            "resume.dlq",
            durable=True,
        )

        await dlq.bind(dlx, routing_key=queue_name)

        return queue


publisher = RabbitMQPublisher()
