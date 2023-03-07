import json
import time

from typing import Optional

import requests


def get_config() -> dict:
    with open('config.json') as f:
        return json.loads(f.read())


def get_url_with_tries(url: str, params: Optional[dict] = None, tries: int = 5, sleep: int = 3):
    counter = 0
    while True:
        counter += 1
        try:
            return requests.get(url=url, params=params).json()
        except:
            if counter > tries:
                raise BaseException
            time.sleep(sleep)
