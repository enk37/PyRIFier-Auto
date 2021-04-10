#!/usr/bin/env python

############################################################################################################################
# pyrifier-auto.py v0.1.5                                                                                                  #
#                                                                                                                          #
# PyEZ RIPE Filter Automation, hence PyRIFier-Auto.                                                                        #
# This is a simple Python RIPE database parsing tool that finds all routes for AS or AS-SET and updates JunOS prefix list. #
# It can be useful for cron based tasks to update your filters automatically                                               #
#                                                                                                                          #
# Written by Eugene Khabarov on 07.08.2020 and published under GPLv3 license                                               #
############################################################################################################################

import sys
import getpass
import os
import json
import argparse
import requests
from requests.exceptions import ConnectTimeout
from jnpr.junos import Device
from jnpr.junos.utils.config import Config
from jnpr.junos.exception import ConfigLoadError
from time import sleep
from inspect import getframeinfo, stack

# Error handling
def onError(exception_type, exception, traceback):
    print "%s: %s" % (exception_type.__name__, exception)
sys.excepthook = onError

#This function resolves AS-SET into list of AS numbers
def resolve_as_set(as_set):
    #define empty list of AS
    as_list = []
    req = "https://rest.db.ripe.net/search.json?type-filter=as-set&type-filter=aut-num&source=ripe&query-string=" + as_set

    #already tried
    tries = 0
    #max number of retries
    req_retries_lim = 3
    while True:
        tries += 1
        try:
            resp = requests.get(req)
            # Get request ok?
            if resp.status_code == 200:
                for x in resp.json()["objects"]["object"]:
                    if x["type"] == "as-set":
                        for y in  x["attributes"]["attribute"]:
                            if y["name"] == "members":
                                if y["referenced-type"] == "aut-num":
                                    as_list.append(y["value"])
                                else:
                                    as_list += resolve_as_set(y["value"])
                    elif x["type"] == "aut-num":
                        for y in  x["attributes"]["attribute"]:
                            if y["name"] == "aut-num":
                                    as_list.append(y["value"])
                    else:
                        continue
                return as_list
            # If not, should we try again later?
            if resp.status_code == 429 and tries < retries_lim:
                try:
                    retry_after = int(resp.headers.get('Retry-After'))
                except Exception:
                    retry_after = 1

                print "notification: Waiting for %s second(s) ..." % retry_after
                sleep(retry_after)
                continue

            # Throw if not ok (2xx). This means something went wrong.
            raise ApiError('GET /tasks/ {}'.format(resp.status_code))

        # Network timeout, should we retry?
        except ConnectTimeout:
            if tries < retries_lim:
                continue
            else:
                raise ApiError('GET /tasks/ {}'.format(resp.status_code))

    return as_list

#This function resolves AS into list of ROUTES
def resolve_routes(aut_num):
    #define empty list of routes
    route_list = []

    req = "https://rest.db.ripe.net/search.json?inverse-attribute=origin&type-filter=route&source=ripe&query-string=" + aut_num

    #already tried
    tries = 0
    #max number of retries
    retries_lim = 3
    while True:
        tries += 1
        try:
            resp = requests.get(req)
            # Get request ok?
            if resp.status_code == 200:
                #get list of routes
                for y in resp.json()["objects"]["object"]:
                    if y["primary-key"]["attribute"][0]["name"] == "route":
                        route_list.append(y["primary-key"]["attribute"][0]["value"])
                return route_list

            # If not, should we try again later?
            if resp.status_code == 429 and tries < retries_lim:
                try:
                    retry_after = int(resp.headers.get('Retry-After'))
                except Exception:
                    retry_after = 1

                print "notification: Waiting for %s second(s) ..." % retry_after
                sleep(retry_after)
                continue

            # Throw if not ok (2xx). This means something went wrong.
            raise ApiError('GET /tasks/ {}'.format(resp.status_code))

            # Network timeout, should we retry?
        except ConnectTimeout:
            if tries < retries_lim:
                continue
            else:
                raise ApiError('GET /tasks/ {}'.format(resp.status_code))

    return route_list

#Main program begins here
cmdline = argparse.ArgumentParser(description="Python RIPE Database Parsing Tool That Finds All ROUTES for AS or AS-SET and Updates JUNOS Prefix Lists")
cmdline.add_argument("-t", metavar="router", help="Target router to connect", required=True)
cmdline.add_argument("-l", metavar="prefix-list", help="prefix-list name", required=True)
cmdline.add_argument("-p", metavar="port", help="NETCONF TCP port, default is 830", default=830)
cmdline.add_argument("-u", metavar="username", help="Remote username", default="auto")
cmdline.add_argument("-k", metavar="keyfile", help="Path to ssh key file, default is ~/.ssh/id_rsa", default="~/.ssh/id_rsa")
cmdline.add_argument("-n", metavar="as-set", help="BGP AS or AS-SET to resolve into corresponding routes", required=False)
cmdline.add_argument("-d", help="delete prefix list or clear it before updating with new data if combined with -n option", default=False, action='store_true')
args=cmdline.parse_args()

if (args.l==None):
        print "Nothing to do!"
        sys.exit(1)

#use ssh key-based autentication only!
dev = Device(host=args.t, user=args.u, port=args.p, ssh_private_key_file=args.k)
dev.open()
#default is 30s, not enough, see https://www.juniper.net/documentation/en_US/junos-pyez/topics/task/troubleshooting/junos-pyez-configuration-errors-troubleshooting.html
dev.timeout = 120

with Config(dev, mode="private") as config:
    if args.l != None:
        if args.d:
            #cleanup prefix-list
            try:
                config.load("delete policy-options prefix-list %s" % (args.l), format="set")
            except ConfigLoadError, e:
                if (e.rpc_error['severity']=='warning'):
                    print "%s" % e.message
                else:
                    raise

        if args.n:
            #define empty list of routes
            routes = []
            #iterate through AS/AS-SET
            for x in resolve_as_set(args.n):
                #here extend needed instead of append to join lists into one flat list
                routes.extend(resolve_routes(x))

            #iterate through list of routes and add to the prefix-list
            for p in routes:
                try:
                    config.load("set policy-options prefix-list %s %s" % (args.l, p), format="set")
                except ConfigLoadError, e:
                    if (e.rpc_error['severity']=='warning'):
                       print ": %s" % e.message
                    else:
                       raise

        #finally show the config diff and commit
        diff = config.diff()
        if diff != None:
                print diff
                config.commit()
        else:
            print "notification: no changes were made"

dev.close()
