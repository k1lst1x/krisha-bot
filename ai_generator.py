from __future__ import annotations

import logging
import os
from pathlib import Path

from scraper import Listing


LOGGER = logging.getLogger(__name__)


class MessageGenerator:
    def __init__(
        self,
        goal: str,
        model: str,
        max_message_chars: int = 450,
        prompt_path: Path | None = None,
    ) -> None:
        self.goal = goal
        self.model = model
        self.max_message_chars = max_message_chars
        self.prompt_template = self._load_prompt(prompt_path)
        self._client = self._build_client()

    def generate(self, listing: Listing) -> str:
        if self._client is None:
            return self._fallback_message(listing)

        prompt = self.prompt_template.format(
            title=listing.title or "не указано",
            district=listing.district or "не указан",
            price=listing.price or "не указана",
            goal=self.goal,
        )

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Пиши только финальный текст сообщения владельцу. "
                            "Не добавляй пояснения, списки или варианты."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            message = response.choices[0].message.content.strip()
            return self._limit_message(message)
        except Exception as exc:  # OpenAI SDK exceptions vary across major versions.
            LOGGER.warning("OpenAI generation failed, using fallback: %s", exc)
            return self._fallback_message(listing)

    def _build_client(self):
        if not os.getenv("OPENAI_API_KEY"):
            LOGGER.info("OPENAI_API_KEY is empty, using fallback generator")
            return None

        try:
            from openai import OpenAI

            return OpenAI()
        except Exception as exc:
            LOGGER.info("OpenAI client is unavailable, using fallback generator: %s", exc)
            return None

    def _load_prompt(self, prompt_path: Path | None) -> str:
        if prompt_path and prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")

        return (
            "Напиши короткое деловое сообщение владельцу объявления.\n"
            "Заголовок: {title}\n"
            "Район: {district}\n"
            "Цена: {price}\n"
            "Цель контакта: {goal}\n"
        )

    def _fallback_message(self, listing: Listing) -> str:
        area = f" в районе {listing.district}" if listing.district else ""
        price = f" Цена указана: {listing.price}." if listing.price else ""
        message = (
            f"Здравствуйте. Увидел ваше объявление{area}, хотел бы уточнить детали. "
            f"{price} {self.goal}."
        )
        return self._limit_message(message)

    def _limit_message(self, message: str) -> str:
        normalized = " ".join(message.split())
        if len(normalized) <= self.max_message_chars:
            return normalized
        return normalized[: self.max_message_chars].rstrip(" .,;") + "."
