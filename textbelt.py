#!/usr/bin/env python3

from typing import Optional, Tuple
import time
import requests

TEXTBELT_URL = "https://textbelt.com"


class Textbelt():

    class TextError(Exception):
        def __init__(self, message):
            super().__init__(message)


    class Text():
        def __init__(self, text_id: str, textbelt: "Textbelt") -> None:
            self.text_id = text_id
            self.textbelt = textbelt

        def status(self) -> str:
            return self.textbelt.text_status(self.text_id)

        def _is_received(self, status: str) -> bool:
            return status == "DELIVERED"

        def received(self) -> bool:
            return self._is_received(self.status())

        def wait_until_received(self, timeout: int = 10) -> Tuple[bool, str]:
            start = time.time()
            last_status = "UNKNOWN"
            while time.time() - start < timeout:
                last_status = self.status()
                if self._is_received(last_status):
                    return True, last_status
            return False, last_status

    def __init__(self, api_key: Optional[str]) -> None:
        self.api_key = api_key

    def send(self, number: str, text: str) -> Text:
        resp = requests.post(f"{TEXTBELT_URL}/text", {
            "phone": number,
            "message": text,
            "key": "textbelt",
        }, timeout=10).json()

        if not resp["success"]:
            errmsg = resp["error"]
            raise RuntimeError(
                f"Could not send SMS to {number} with api key '{self.api_key}': {errmsg}")

        return Textbelt.Text(resp["textId"], self)

    def text_status(self, text_id: str) -> str:
        resp = requests.get(f"{TEXTBELT_URL}/status/{text_id}", timeout=10).json()
        return resp["status"]

    def quota(self) -> int:
        resp = requests.get(f"{TEXTBELT_URL}/quota/{self.api_key}", timeout=10).json()
        if not resp["success"]:
            raise RuntimeError(f"Could not check Textbelt quota for {self.api_key}")
        return resp["quotaRemaining"]
