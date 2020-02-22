#!/usr/bin/env python3
# -*-coding:UTF-8 -*

import os
import re
import sys
import time
import redis
import datetime

sys.path.append(os.path.join(os.environ['AIL_BIN'], 'packages/'))
import Item
import Tag
from Cryptocurrency import cryptocurrency
from Pgp import pgp

sys.path.append(os.path.join(os.environ['AIL_BIN'], 'lib/'))
import ConfigLoader
import Decoded
import Domain

def update_update_stats():
    nb_updated = int(r_serv_db.get('update:nb_elem_converted'))
    progress = int((nb_updated * 100) / nb_elem_to_update)
    print('{}/{}    updated    {}%'.format(nb_updated, nb_elem_to_update, progress))
    r_serv_db.set('ail:current_background_script_stat', progress)

def update_domain_by_item(domain_obj, item_id):
    domain_name = domain_obj.get_domain_name()
    # update domain tags
    for tag in Tag.get_obj_tag(item_id):
        if tag != 'infoleak:submission="crawler"' and tag != 'infoleak:submission="manual"':
            Tag.add_tag("domain", tag, domain_name, obj_date=Item.get_item_date(item_id))

    # update domain correlation
    item_correlation = Item.get_item_all_correlation(item_id)

    for correlation_name in item_correlation:
        for correlation_type in item_correlation[correlation_name]:
            if correlation_name in ('pgp', 'cryptocurrency'):
                for correl_value in item_correlation[correlation_name][correlation_type]:
                    if correlation_name=='pgp':
                        pgp.save_domain_correlation(domain_name, correlation_type, correl_value)
                    if correlation_name=='cryptocurrency':
                        cryptocurrency.save_domain_correlation(domain_name, correlation_type, correl_value)
            if correlation_name=='decoded':
                for decoded_item in item_correlation['decoded']:
                    Decoded.save_domain_decoded(domain_name, decoded_item)

if __name__ == '__main__':

    start_deb = time.time()

    config_loader = ConfigLoader.ConfigLoader()
    r_serv_db = config_loader.get_redis_conn("ARDB_DB")
    r_serv_onion = config_loader.get_redis_conn("ARDB_Onion")
    config_loader = None

    nb_elem_to_update = r_serv_db.get('update:nb_elem_to_convert')
    if not nb_elem_to_update:
        nb_elem_to_update = 0
    else:
        nb_elem_to_update = int(nb_elem_to_update)

    while True:
        domain = r_serv_onion.spop('domain_update_v2.4')
        if domain is not None:
            print(domain)
            domain = Domain.Domain(domain)
            for domain_history in domain.get_domain_history():

                domain_item = domain.get_domain_items_crawled(epoch=domain_history[1]) # item_tag
                if "items" in domain_item:
                    for item_dict in domain_item['items']:
                        update_domain_by_item(domain, item_dict['id'])

            r_serv_db.incr('update:nb_elem_converted')
            update_update_stats()

        else:
            sys.exit(0)
