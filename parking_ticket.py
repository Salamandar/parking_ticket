#!/usr/bin/env python3

from typing import Optional, List, Dict, Any
from functools import cached_property
import datetime
import requests
import yaml

from textbelt import Textbelt

class ParkingTicket():
    auth_url_root = "https://auth.paybyphoneapis.com"
    api_url_root = "https://consumer.paybyphoneapis.com"

    def __init__(self, configuration: Dict[str, str]):
        self.plate_nr = configuration["plate_nr"]
        self.zip_code = configuration["zip_code"]
        self.rate_option = configuration["rate_option"]
        self.login(configuration["username"], configuration["password"])

    def login(self, username: str, password: str):
        response = requests.post(
            f"{self.auth_url_root}/token",
            data={
                "grant_type": "password",
                "username": username,
                "password": password,
                "client_id": "paybyphone_web",
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Pbp-ClientType": "WebApp",
            },
            timeout=2
        )
        response.raise_for_status()
        self.token = response.json()["access_token"]

    def api_request(self, kind: str, path: str,
                    data: Optional[Dict] = None,
                    headers: Optional[Dict] = None,
                    params: Optional[Dict] = None,
                    json: Optional[Dict] = None,
            ):
        if data is None:
            data = {}
        if headers is None:
            headers = {}
        headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.8,en-US;q=0.5,en;q=0.3",
        })

        result = requests.request(
            kind,
            f"{self.api_url_root}/{path}",
            data=data,
            headers=headers,
            timeout=5,
            params=params,
            json=json
        )
        result.raise_for_status()
        return result

    @cached_property
    def account_id(self):
        # FIXME: Assume a single account for now
        result = self.api_request("get", "parking/accounts")
        return result.json()[0]["id"]

    def account_tickets(self):
        result = self.api_request("get", f"parking/accounts/{self.account_id}/sessions?periodType=Current")
        return result.json()

    def pprint_date(self, timestamp: str):
        time = datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S%z")
        return time.astimezone().strftime("%H:%M %d/%m/%Y")

    def pprint_tickets(self, tickets: List[Dict[str, Any]]):
        tickets_data = []
        for ticket in tickets:
            tickets_data.append({
                "Ticket ID": ticket["parkingSessionId"],
                "Code Postal": ticket["locationId"],
                "Début": self.pprint_date(ticket["startTime"]),
                "Fin": self.pprint_date(ticket["expireTime"]),
                "Véhicule": {
                    "ID": ticket["vehicle"]["id"],
                    "Immatriculation": ticket["vehicle"]["licensePlate"],
                    "Type": ticket["vehicle"]["type"],
                },
                "Tarif": ticket["rateOption"]["type"],
            })
        data = {"Tickets courants": tickets_data}
        return yaml.dump(data, indent=4, allow_unicode=True)

    def new_ticket(self, quantity: int, starts_on: str):
        # First get quote… yeah…
        data = {
            "locationId": self.zip_code,
            "licensePlate": self.plate_nr,
            "rateOptionId": self.rate_option,
            "durationTimeUnit": "Days",
            "durationQuantity": str(quantity),
            "isParkUntil": False,
            "parkingAccountId": self.account_id,
        }

        response = self.api_request("get", f"parking/accounts/{self.account_id}/quote", params=data)
        quote_id = response.json()["quoteId"]
        quote_cost = response.json()["totalCost"]

        print(f"Got quote: {quote_id}, for {quote_cost['amount']}{quote_cost['currency']}")
        assert quote_cost["amount"] == 0

        data = {
            "expireTime": None,
            "duration": {
                "quantity": str(quantity),
                "timeUnit": "days"
            },
            "licensePlate": self.plate_nr,
            "locationId": self.zip_code,
            "rateOptionId": self.rate_option,
            "startTime": starts_on,  # 2023-03-16T21:41:52Z ???
            "quoteId": quote_id,
            "parkingAccountId": self.account_id,
        }

        # Requesting the session...
        response = self.api_request("post", f"parking/accounts/{self.account_id}/sessions/", json=data)

        # Waiting for the workflow to finish...
        workflow_url = response.headers["Location"].split(f"{self.api_url_root}/")[1]
        session_workflow = True
        while session_workflow:
            print("Attente du traitement...")
            response = self.api_request("get", workflow_url)
            # print(response.text)
            for response_item in response.json():
                if "StartParkingFailed" in response_item.get("$type"):
                    print(f"Échec de réservation de ticket ! Raison : {response_item['failureReason']}")
                    session_workflow = False
                if "FreeParkingSessionCreated" in response_item.get("$type"):
                    session_workflow = False
                    print("Ticket pris avec succès !")


        print(self.pprint_tickets(self.account_tickets()))
        # return response.text


def main():
    with open("configuration.yaml", "r", encoding="utf-8") as configuration_file:
        configuration = yaml.load(configuration_file, Loader=yaml.SafeLoader)

    paybyphone_config = configuration["paybyphone"]
    parking_ticket = ParkingTicket(paybyphone_config)

    print(f"Account ID: {parking_ticket.account_id}")
    print(parking_ticket.pprint_tickets(parking_ticket.account_tickets()))

    time_start_ticket = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    parking_ticket.new_ticket(1, time_start_ticket)

    textbelt_config = configuration["textbelt"]
    if textbelt_config.get("notify"):
        textbelt = Textbelt(textbelt_config["key"])
        text = textbelt.send(textbelt_config["number"], "Ticket pris aujourd'hui!")
        received, status = text.wait_until_received()
        if not received:
            print(f"Text message not received in 10s, status was {status}")


if __name__ == "__main__":
    main()
