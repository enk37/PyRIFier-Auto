#!/usr/bin/env python

##########################################################################################################################
# pyrifier-auto.py v0.1.1                                                                                                  #
#                                                                                                                        #
# PyEZ RIPE Filter Automation, hence PyRIFier-Auto.                                                                      #
# This is simple Python RIPE database parsing tool that finds all routes for AS or AS-SET and updates JunOS prefix list. #
# It can be useful for cron based tasks to update your filters automatically                                             #
#                                                                                                                        #
# Written by Eugene Khabarov on 07.08.2020 and published under GPLv3 license                                             #
##########################################################################################################################

import sys
import getpass
import os
import json
import argparse
import requests
from jnpr.junos import Device
from jnpr.junos.utils.config import Config
from jnpr.junos.exception import ConfigLoadError

# Error handling
def onError(exception_type, exception, traceback):
    print "%s: %s" % (exception_type.__name__, exception)
sys.excepthook = onError

#This function resolves AS-SET into list of AS numbers
def resolve_as_set(as_set):
    as_list = []
    req = "https://rest.db.ripe.net/search.json?type-filter=as-set&type-filter=aut-num&source=ripe&query-string=" + as_set
    resp = requests.get(req)

    if resp.status_code != 200:
        # This means something went wrong.
        raise ApiError('GET /tasks/ {}'.format(resp.status_code))

    for x in resp.json()["objects"]["object"]:
        if x["type"] == "as-set":
            for y in  x["attributes"]["attribute"]:
                if y["name"] == "members":
                    if y["referenced-type"] == "aut-num":
                        as_list.append(y["value"])
                    else:
                        resolve_as_set(y["value"])
        elif x["type"] == "aut-num":
            for y in  x["attributes"]["attribute"]:
                if y["name"] == "aut-num":
                        as_list.append(y["value"])
        else:
            continue
    return as_list

#Main program begins here
cmdline = argparse.ArgumentParser(description="Python RIPE Database Parsing Tool That Finds All ROUTES for AS or AS-SET and Updates JUNOS Prefix Lists")
cmdline.add_argument("-t", metavar="router", help="Target router to connect", required=True)
cmdline.add_argument("-l", metavar="prefix-list", help="prefix-list name", required=True)
cmdline.add_argument("-p", metavar="port", help="NETCONF TCP port, default is 830", default=830)
cmdline.add_argument("-u", metavar="username", help="Remote username", default="auto")
cmdline.add_argument("-n", metavar="as-set", help="BGP AS or AS-SET to resolve into corresponding routes", required=True)
cmdline.add_argument("-d", help="clear/delete prefix list before updating with new data", default=False, action='store_true')
args=cmdline.parse_args()

if (args.n==None):
        print "Nothing to do!"
        sys.exit(1)

#use ssh key-based autentication only!
dev = Device(host=args.t, user=args.u, port=args.p)
dev.open()
#default is 30s, not enough, see https://www.juniper.net/documentation/en_US/junos-pyez/topics/task/troubleshooting/junos-pyez-configuration-errors-troubleshooting.html
dev.timeout = 120

with Config(dev, mode="private") as config:
    if args.n!=None:
        #define empty list of routes
        routes = []
        if args.d:
            #cleanup prefix-list
            try:
                config.load("delete policy-options prefix-list %s" % (args.l), format="set")
            except ConfigLoadError, e:
                if (e.rpc_error['severity']=='warning'):
                    print "Warning: %s" % e.message
                else:
                    raise
        #iterate through AS/AS-SET
        for x in resolve_as_set(args.n):
            req = "https://rest.db.ripe.net/search.json?inverse-attribute=origin&type-filter=route&source=ripe&query-string=" + x
            resp = requests.get(req)

            if resp.status_code != 200:
                raise ApiError('GET /tasks/ {}'.format(resp.status_code))
            #get list of routes
            for y in resp.json()["objects"]["object"]:
                routes.append(y["primary-key"]["attribute"][0]["value"])

        #iterate through list of routes and add to the prefix-list
        for p in routes:
            try:
                config.load("set policy-options prefix-list %s %s" % (args.l, p), format="set")
            except ConfigLoadError, e:
                if (e.rpc_error['severity']=='warning'):
                   print "Warning: %s" % e.message
                else:
                   raise
        #finally show the config diff and commit
        diff = config.diff()
        if (diff!=None):
                print diff
        config.commit()

dev.close()
