import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aio_pika
from aio_pika import ExchangeType

from resume_ai.core.config import settings

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


class RabbitMQConsumer:
    DEAD_LETTER_EXCHANGE = "resume.dlx"
    DEAD_LETTER_QUEUE = "resume.dlq"

    def __init__(self, queue_name: str) -> None:
        self.queue_name = queue_name
        self.connection = None
        self.channel = None

    async def start(self, handler: MessageHandler) -> None:
        self.connection = await aio_pika.connect_robust(
            settings.rabbitmq_url
        )

        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=1)

        # Failed messages go to the dead-letter queue.
        dead_letter_exchange = await self.channel.declare_exchange(
            self.DEAD_LETTER_EXCHANGE,
            ExchangeType.DIRECT,
            durable=True,
        )

        dead_letter_queue = await self.channel.declare_queue(
            self.DEAD_LETTER_QUEUE,
            durable=True,
        )

        await dead_letter_queue.bind(
            dead_letter_exchange,
            routing_key=self.queue_name,
        )

        queue = await self.channel.declare_queue(
            self.queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": self.DEAD_LETTER_EXCHANGE,
                "x-dead-letter-routing-key": self.queue_name,
            },
        )

        async def process_message(message: aio_pika.abc.AbstractIncomingMessage):
            try:
                payload = json.loads(message.body.decode())

                if not isinstance(payload, dict):
                    raise ValueError("Message payload must be a JSON object")

                await handler(payload)

            except Exception:
                logger.exception(
                    "Failed processing message from %s",
                    self.queue_name,
                )
                await message.reject(requeue=False)

            else:
                await message.ack()

        await queue.consume(process_message)

        logger.info("Consuming messages from %s", self.queue_name)

        try:
            await asyncio.Future()
        finally:
            await self.close()

    async def close(self) -> None:
        if self.connection and not self.connection.is_closed:
            await self.connection.close()