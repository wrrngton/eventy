import argparse
import json
import math
import os
import random
import re
import sys
import time
import urllib
import uuid

import tomli as tomllib
from algoliasearch.insights.client import InsightsClientSync
from algoliasearch.search.client import SearchClientSync

app_config = {}
count = 0

# Algolia
app = {}
insights = {}
accrued_searches = []


def init_algolia():
    app_id = app_config["app"]["app_id"]
    public_key = app_config["app"]["public_key"]

    client = SearchClientSync(app_id, public_key)
    insights = InsightsClientSync(app_id, public_key)
    return client, insights


def perform_query(query: str, payload: dict) -> dict:
    index = app_config["app"]["index"]
    res = app.search_single_index(index_name=index, search_params=payload)
    return res


def form_and_send_events():
    global insights
    ctr = app_config["config"]["ctr"]
    cvr = app_config["config"]["cvr"]
    num_searches = app_config["config"]["num_searches"]
    algolia_index = app_config["app"]["index"]

    accrued_events = []
    no_result_count = 0
    random.shuffle(accrued_searches)

    click_every = int(math.ceil(100 / ctr))
    conv_every = int(math.ceil(100 / cvr))

    inner_count = 0

    while inner_count < num_searches:

        item = accrued_searches[inner_count]
        hits = item["hits"]

        if not item["hits"]:
            no_result_count = no_result_count + 1

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
                    "eventName": "items clicked",
                    "eventType": "click",
                    "index": algolia_index,
                    "objectIDs": [chosen_hit["objectID"]],
                    "positions": [rand_id + 1],
                    "queryID": item["queryID"],
                    "userToken": item["userToken"],
                }
                accrued_events.append(click_event)

            if inner_count % conv_every == 0:

                hits_len = len(hits)
                hits_top_10 = int(0.10 * hits_len)
                hits_weights = [10] * hits_top_10 + [1] * (hits_len - hits_top_10)
                rand_id = random.choices(
                    list(range(hits_len)), weights=hits_weights, k=1
                )[0]

                chosen_hit = hits[rand_id]

                conv_event = {
                    "eventName": "items purchased",
                    "eventType": "conversion",
                    "eventSubType": "purchase",
                    "index": algolia_index,
                    "objectIDs": [chosen_hit["objectID"]],
                    "queryID": item["queryID"],
                    "userToken": item["userToken"],
                    "objectData": [
                        {
                            "price": float(chosen_hit["price"]),
                            "quantity": 1
                        }
                    ],
                    "value": float(chosen_hit["price"]),
                    "currency": app_config["config"]["currency"]
                }

                accrued_events.append(conv_event)

        inner_count += 1

    chunk_size = 10
    chunked_arr = [
        accrued_events[i : i + chunk_size]
        for i in range(0, len(accrued_events), chunk_size)
    ]

    for arr in chunked_arr:
        insights.push_events(insights_events={"events": arr})

    return no_result_count


def form_search_dicts(q_ID: str, hits: list, u_ID: str, text_query: str) -> dict:
    price_attr = app_config["config"]["price_attr"]
    hits_arr = []
    search_dict = {}

    if "." in price_attr:
        x = price_attr.split(".")
        atty = x[0]
        nest = x[1]
        hits_arr = [
            {"objectID": h.object_id, "price": getattr(h, atty)[nest]} for h in hits
        ]

    else:
        hits_arr = [{"objectID": h.object_id, "price": h.price_attr} for h in hits]

    search_dict["hits"] = hits_arr
    search_dict["queryID"] = q_ID
    search_dict["userToken"] = u_ID
    search_dict["query"] = text_query


    return search_dict


def construct_param_dict(params):
    q_arr = params.split("&")
    new_obj = {}
    for item in q_arr:
        c = item.split("=")
        if len(c) == 1:
            continue
        new_obj[c[0]] = c[1]
    return new_obj


def construct_query(type, search_count) -> dict:
    pers_freq = app_config["config"]["pers_freq"]
    num_profiles = len(app_config["profiles"])
    perso_list = app_config["profiles"]
    filters_list = app_config["filters"]
    query_list = app_config["searches"]
    num_filters = len(app_config["filters"])
    num_queries = len(app_config["searches"])
    queries_top_10 = math.ceil(0.10 * num_queries)
    filters_top_10 = math.ceil(0.10 * num_filters)
    search_weights = [10] * queries_top_10 + [5] * (num_queries - queries_top_10)
    filter_weights = [10] * filters_top_10 + [5] * (num_filters - filters_top_10)
    category_id = app_config["config"]["category_id"]
    price_attr = app_config["config"]["price_attr"]

    token = uuid.uuid4()
    filter = ""
    eligible_analytics_tags = ["mobile", "desktop", "ios", "android"]
    analytics_tags = [
        eligible_analytics_tags[random.randint(0, len(eligible_analytics_tags) - 1)],
    ]

    if search_count % pers_freq == 0:
        random_int = random.randint(0, num_profiles - 1)
        random_user = perso_list[random_int]
        token = random_user["userToken"]

    for user in perso_list:
        if token == user["userToken"]:
            analytics_tags.append(f"user: {token}")

    payload = {
        "analytics": True,
        "attributesToHighlight": [],
        "hitsPerPage": 100,
        "clickAnalytics": True,
        "attributesToRetrieve": ["objectID", price_attr],
        "userToken": str(token),
        "analyticsTags": analytics_tags,
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
            list(range(num_queries)), weights=search_weights, k=1
        )[0]
        text_value = query_list[random_index]
        query = text_value

    return payload, query


def perform():
    global count
    num_searches = app_config["config"]["num_searches"]
    browse_freq = app_config["config"]["browse_freq"]

    while count < num_searches:

        if count == 0:
            print("running queries...")

        if count % browse_freq == 0:
            payload, query = construct_query("browse", count)
            response = perform_query(query, payload)
            param_dict = construct_param_dict(response.params)
            userT = param_dict["userToken"]
            searches = form_search_dicts(response.query_id, response.hits, userT, query)
            accrued_searches.append(searches)

        else:
            payload, query = construct_query("text", count)
            response = perform_query(query, payload)
            param_dict = construct_param_dict(response.params)
            userT = param_dict["userToken"]
            searches = form_search_dicts(response.query_id, response.hits, userT, query)
            accrued_searches.append(searches)

        count += 1

        if count == num_searches:

            print("finished running queries, now formulating events")

            no_results_count = form_and_send_events()

            print(
                f"""finished running events, check your dashboard debugger. {
                    no_results_count} queries didn't return any results"""
            )


def config():
    parser = argparse.ArgumentParser(description="Run script with a config directory.")
    parser.add_argument(
        "--config-dir", type=str, required=True, help="Path to directory"
    )

    args = parser.parse_args()
    config_dir = args.config_dir
    config_path = os.path.join("configs", config_dir)

    if not os.path.isdir(config_path):
        raise ValueError(
            f"""Provided path {
                config_dir} is not a valid directory"""
        )

    config = "config.toml"
    config_data = {}

    with open(os.path.join(config_path, config), "r", encoding="utf-8") as f:
        data = tomllib.loads(f.read())
        config_data = data

    searches = config_data["files"]["searches"]
    filters = config_data["files"]["filters"]
    profiles = config_data["files"]["profiles"]

    query_list = json.loads(
        open(os.path.join(config_path, searches), "r", encoding="utf-8").read()
    )

    random.shuffle(query_list)

    filters_list = json.loads(
        open(os.path.join(config_path, filters), "r", encoding="utf-8").read()
    )

    perso_list = json.loads(
        open(os.path.join(config_path, profiles), "r", encoding="utf-8").read()
    )

    config_data["searches"] = query_list
    config_data["filters"] = filters_list
    config_data["profiles"] = perso_list

    return config_data


def main():
    global app_config
    global app
    global insights

    app_config = config()
    app, insights = init_algolia()

    perform()


if __name__ == "__main__":
    main()
