#!/usr/bin/env python
import datetime
import time
import json
import urllib2
#import urllib3 as urllib2
#import urllib.request as urllib2 
import os
import sys
import ssl
import certifi
import base64

#ssl.SSLContext.verify_mode = ssl.VerifyMode.CERT_OPTIONAL
#ssl.SSLContext.verify_mode = ssl.VerifyMode.CERT_NONE

#ssl._create_default_https_context = ssl._create_unverified_context
#scontext = ssl.SSLContext(ssl.PROTOCOL_TLS)
#scontext.verify_mode = ssl.VerifyMode.CERT_NONE

#ssl._create_default_https_context = ssl._create_stdlib_context

#if (not os.environ.get('PYTHONHTTPSVERIFY', '') and getattr(ssl, '_create_unverified_context', None)):
#   ssl._create_default_https_context = ssl._create_unverified_context

#context = ssl._create_unverified_context()

# ElasticSearch Cluster to Monitor
elasticServer = os.environ.get('ES_METRICS_CLUSTER_URL', 'https://localhost:9200')
interval = int(os.environ.get('ES_METRICS_INTERVAL', '60'))

# ElasticSearch Cluster to Send Metrics
elasticIndex = os.environ.get('ES_METRICS_INDEX_NAME', 'elasticsearch_metrics')
elasticMonitoringCluster = os.environ.get('ES_METRICS_MONITORING_CLUSTER_URL', 'https://localhost:9200')

# Enable Elasticsearch Security
# read_username and read_password for read ES cluster information
# write_username and write_passowrd for write monitor metric to ES.
read_es_security_enable = True
read_username = 'es_admin'
read_password = 'es_admin'

write_es_security_enable = True
write_username = 'es_admin'
write_password = 'es_admin'

def handle_urlopen(urlData, read_username, read_password):
    if read_es_security_enable: 
      try:
        password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, urlData, read_username, read_password)
        handler = urllib2.HTTPBasicAuthHandler(password_mgr)
        opener = urllib2.build_opener(handler)
        urllib2.install_opener(opener)
        #response = urllib2.urlopen(urlData, cafile='/etc/ssl/certs/ca-certificates.crt')

        request = urllib2.Request(urlData)
        base64string = base64.encodestring('%s:%s' % (read_username, read_password)).replace('\n', '')
        request.add_header("Authorization", "Basic %s" % base64string)
        response = urllib2.urlopen(request, cafile='/usr/share/elasticsearch/certs/ca/ca-includes-privatekey.pem')

        #response = urllib2.urlopen(urlData, context=ssl.create_default_context(cafile=certifi.where()))
        #response = urllib2.urlopen(urlData)
        return response
      except Exception as e:
        print ("Error:  {0}".format(str(e)))
    else:
      try:
        response = urllib2.urlopen(urlData)
        return response
      except Exception as e:
        print ("Error:  {0}".format(str(e)))

def fetch_clusterhealth():
    try:
        utc_datetime = datetime.datetime.utcnow()
        endpoint = "/_cluster/health"
        urlData = elasticServer + endpoint
        response = handle_urlopen(urlData,read_username,read_password)
        jsonData = json.loads(response.read())
        clusterName = jsonData['cluster_name']
        jsonData['@timestamp'] = str(utc_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3])
        if jsonData['status'] == 'green':
            jsonData['status_code'] = 0
        elif jsonData['status'] == 'yellow':
            jsonData['status_code'] = 1
        elif jsonData['status'] == 'red':
            jsonData['status_code'] = 2
        post_data(jsonData)
        return clusterName
    except IOError as err:
        print ("IOError: Maybe can't connect to elasticsearch.")
        clusterName = "unknown"
        return clusterName


def fetch_clusterstats():
    utc_datetime = datetime.datetime.utcnow()
    endpoint = "/_cluster/stats"
    urlData = elasticServer + endpoint
    response = handle_urlopen(urlData,read_username,read_password)
    jsonData = json.loads(response.read())
    jsonData['@timestamp'] = str(utc_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3])
    post_data(jsonData)


def fetch_nodestats(clusterName):
    utc_datetime = datetime.datetime.utcnow()
    endpoint = "/_cat/nodes?v&h=n"
    urlData = elasticServer + endpoint
    response = handle_urlopen(urlData,read_username,read_password)
    nodes = response.read()[1:-1].strip().split('\n')
    for node in nodes:
        endpoint = "/_nodes/%s/stats" % node.rstrip()
        urlData = elasticServer + endpoint
        response = handle_urlopen(urlData,read_username,read_password)
        jsonData = json.loads(response.read())
        nodeID = jsonData['nodes'].keys()
        try:
            jsonData['nodes'][nodeID[0]]['@timestamp'] = str(utc_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3])
            jsonData['nodes'][nodeID[0]]['cluster_name'] = clusterName
            newJsonData = jsonData['nodes'][nodeID[0]]
            post_data(newJsonData)
        except:
            continue


def fetch_indexstats(clusterName):
    utc_datetime = datetime.datetime.utcnow()
    endpoint = "/_stats"
    urlData = elasticServer + endpoint
    response = handle_urlopen(urlData,read_username,read_password)
    jsonData = json.loads(response.read())
    jsonData['_all']['@timestamp'] = str(utc_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3])
    jsonData['_all']['cluster_name'] = clusterName
    post_data(jsonData['_all'])


def post_data(data):
    utc_datetime = datetime.datetime.utcnow()
    url_parameters = {'cluster': elasticMonitoringCluster, 'index': elasticIndex,
        'index_period': utc_datetime.strftime("%Y.%m.%d"), }
    url = "%(cluster)s/%(index)s-%(index_period)s/message" % url_parameters
    headers = {'content-type': 'application/json'}
    try:
        req = urllib2.Request(url, headers=headers, data=json.dumps(data))
        if write_es_security_enable:
            password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
            password_mgr.add_password(None, url, write_username, write_password)
            handler = urllib2.HTTPBasicAuthHandler(password_mgr)
            opener = urllib2.build_opener(handler)
            urllib2.install_opener(opener)

            #request = urllib2.Request(urlData)
            base64string = base64.encodestring('%s:%s' % (write_username, write_password)).replace('\n', '')
            req.add_header("Authorization", "Basic %s" % base64string)
            #response = urllib2.urlopen(req, cafile='/usr/share/elasticsearch/certs/ca/ca-includes-privatekey.pem')

            response = urllib2.urlopen(req, cafile='/usr/share/elasticsearch/certs/ca/ca.crt')
            #response = urllib2.urlopen(req)
        else:
            response = urllib2.urlopen(req)
    except Exception as e:
        print ("Error:  {0}".format(str(e)))


def main():
    clusterName = fetch_clusterhealth()
    if clusterName != "unknown":
        fetch_clusterstats()
        fetch_nodestats(clusterName)
        fetch_indexstats(clusterName)


if __name__ == '__main__':
    try:
        nextRun = 0
        while True:
            if time.time() >= nextRun:
                nextRun = time.time() + interval
                now = time.time()
                main()
                elapsed = time.time() - now
                print ("Total Elapsed Time: %s" % elapsed)
                timeDiff = nextRun - time.time()

                # Check timediff , if timediff >=0 sleep, if < 0 send metrics to es
                if timeDiff >= 0:
                    time.sleep(timeDiff)

    except KeyboardInterrupt:
        print ('Interrupted')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
