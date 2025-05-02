import json
import math
import os
import random
import re
import time
import tomllib
import urllib
import uuid
from typing import Optional

from algoliasearch.insights_client import InsightsClient
from algoliasearch.search_client import SearchClient

processingTimeMS: Optional[int] = None


# Get config info
config = "config.toml"
config_data = {}

with open(config, "r", encoding="utf-8") as f:
    data = tomllib.loads(f.read())
    config_data = data

app_id = config_data["app"]["app_id"]
public_key = config_data["app"]["public_key"]
algolia_index = config_data["app"]["index"]

searches = config_data["files"]["searches"]
filters = config_data["files"]["filters"]
profiles = config_data["files"]["profiles"]

browse_freq = config_data["config"]["browse_freq"]
category_id = config_data["config"]["category_id"]
category_is_array = config_data["config"]["category_is_array"]
num_searches = config_data["config"]["num_searches"]
ctr = config_data["config"]["ctr"]
cvr = config_data["config"]["cvr"]

# Load searches and filters into lists
query_list = json.loads(
    open(os.path.join("configs", searches), "r", encoding="utf-8").read()
)
random.shuffle(query_list)
filters_list = json.loads(
    open(os.path.join("configs", filters), "r", encoding="utf-8").read()
)

# List lengths
num_queries = len(query_list)
num_filters = len(filters_list)


# Apply weighting to top 10% of each list
queries_top_10 = math.ceil(0.10 * num_queries)
filters_top_10 = math.ceil(0.10 * num_filters)
search_weights = [10] * queries_top_10 + [5] * (num_queries - queries_top_10)
filter_weights = [10] * filters_top_10 + [5] * (num_filters - filters_top_10)

# Store all searches in this list
accrued_searches = []

# Algolia
client = SearchClient.create(app_id, public_key)
index = client.init_index(algolia_index)

insights = InsightsClient.create(app_id, public_key)


def perform_query(query: str, payload: dict) -> dict:
    res = index.search(query, payload)
    return res


def construct_query(type) -> dict:
    payload = {
        "analytics": True,
        "attributesToHighlight": [],
        "hitsPerPage": 100,
        "clickAnalytics": True,
        "attributesToRetrieve": ["objectID"],
        "userToken": uuid.uuid4(),
    }

    query = ""

    if type == "browse":
        random_index = random.choices(
            list(range(num_filters)), weights=filter_weights, k=1
        )[0]
        cat_value = filters_list[random_index]
        payload["filters"] = f"{category_id}:'{cat_value}'"

    else:
        random_index = random.choices(
            list(range(num_filters)), weights=filter_weights, k=1
        )[0]
        text_value = query_list[random_index]
        query = text_value

    return payload, query


def form_and_send_events():
    accrued_events = []
    random.shuffle(accrued_searches)

    click_every = int(math.ceil(100 / ctr))
    conv_every = int(math.ceil(100 / cvr))

    inner_count = 0

    while inner_count < num_searches:

        item = accrued_searches[inner_count]
        hits = item["hits"]

        if not item["hits"]:
            print("no hits")

        else:

            if inner_count % click_every == 0:
                hits_len = len(hits)
                hits_top_10 = int(0.10 * hits_len)
                hits_weights = [10] * hits_top_10 + [1] * (hits_len - hits_top_10)
                rand_id = random.choices(
                    list(range(hits_len)), weights=hits_weights, k=1
                )[0]

                chosen_hit = hits[rand_id]

                click_event = {
                    "eventName": "click",
                    "indexName": algolia_index,
                    "objectIDs": [chosen_hit],
                    "positions": [rand_id + 1],
                    "queryID": item["queryID"],
                }
                accrued_events.append(click_event)

                insights.user(item["userToken"]).clicked_object_ids_after_search(
                    "click",
                    algolia_index,
                    [chosen_hit],
                    [rand_id + 1],
                    item["queryID"],
                )

            if inner_count % conv_every == 0:

                hits_len = len(hits)
                hits_top_10 = int(0.10 * hits_len)
                hits_weights = [10] * hits_top_10 + [1] * (hits_len - hits_top_10)
                rand_id = random.choices(
                    list(range(hits_len)), weights=hits_weights, k=1
                )[0]

                chosen_hit = hits[rand_id]

                conv_event = {
                    "eventName": "conversion",
                    "indexName": algolia_index,
                    "objectIDs": [chosen_hit],
                    "queryID": item["queryID"],
                }

                accrued_events.append(conv_event)

                insights.user(item["userToken"]).converted_object_ids_after_search(
                    "conversion",
                    algolia_index,
                    [chosen_hit],
                    item["queryID"],
                )

        inner_count += 1

def form_search_dicts(q_ID: str, hits: list, u_ID: str, text_query: str) -> dict:
    search_dict = {}
    hits_arr = [h["objectID"] for h in hits]
    search_dict["hits"] = hits_arr
    search_dict["queryID"] = q_ID
    search_dict["userToken"] = u_ID
    search_dict["query"] = text_query

    return search_dict


# Perform searches
count = 0

while count < num_searches:

    if count % browse_freq == 0:
        payload, query = construct_query("browse")
        response = perform_query(query, payload)
        match = re.search(r"userToken=([0-9a-fA-F\-]{36})", response["params"])
        userT = match.group(1)
        searches = form_search_dicts(
            response["queryID"], response["hits"], userT, query
        )
        accrued_searches.append(searches)

    else:
        payload, query = construct_query("text")
        response = perform_query(query, payload)
        searches = form_search_dicts(
            response["queryID"], response["hits"], userT, query
        )
        accrued_searches.append(searches)

    count += 1

    if count == num_searches:

        print("finished running queries, now formulating events")

        form_and_send_events()

        print("finished running events, check your dashboard debugger")
