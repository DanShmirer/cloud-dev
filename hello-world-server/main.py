import os
import logging
from sys import stdout
from flask import Flask, request

app = Flask(__name__)

logger = logging.getLogger('hw-logger')
logger.setLevel(logging.DEBUG) # set logger level
logFormatter = logging.Formatter\
("%(name)-12s %(asctime)s %(levelname)-8s %(filename)s:%(funcName)s %(message)s")
consoleHandler = logging.StreamHandler(stdout) #set streamhandler to stdout
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)


@app.route('/hw', methods=['GET'])
def profileQuery():
    logger.info(" route: /hw, method: GET")
    return "Hello World!\n"


if __name__ == '__main__':
    try:
        p = os.getenv("FLASK_SERVER_PORT", 5000)
        app.run(host="0.0.0.0", port=p)
    except Exception as e:
        logger.error(e)


# query
# Provides statistics about the execution of an entire Flux script. When enabled, results include a table with the following columns:

# TotalDuration: total query duration in nanoseconds.
# CompileDuration: number of nanoseconds spent compiling the query.
# QueueDuration: number of nanoseconds spent queueing.
# RequeueDuration: number fo nanoseconds spent requeueing.
# PlanDuration: number of nanoseconds spent planning the query.
# ExecuteDuration: number of nanoseconds spent executing the query.
# Concurrency: number of goroutines allocated to process the query.
# MaxAllocated: maximum number of bytes the query allocated.
# TotalAllocated: total number of bytes the query allocated (includes memory that was freed and then used again).
# RuntimeErrors: error messages returned during query execution.
# flux/query-plan: Flux query plan.
# influxdb/scanned-values: value scanned by InfluxDB.
# influxdb/scanned-bytes: number of bytes scanned by InfluxDB.
# operator
# The operator profiler output statistics about each operation in a query. Operations executed in the storage tier return as a single operation. When the operator profile is enabled, results include a table with a row for each operation and the following columns:

# Type: operation type
# Label: operation name
# Count: total number of times the operation executed
# MinDuration: minimum duration of the operation in nanoseconds
# MaxDuration: maximum duration of the operation in nanoseconds
# DurationSum: total duration of all operation executions in nanoseconds
# MeanDuration: average duration of all operation executions in nanoseconds


# CURL

# curl -XPOST -H "Content-Type: application/json" "http://$(kubectl get nodes -A -o wide | grep ric | awk '{print $6}'):$(kubectl get services -A | grep -e profiler | awk '{print $6}' | cut -d':' -f4 |cut -d'/' -f1)/query" -d "{\"query\": \"from(bucket: 'pw-kpi') \
# |> range(start:-10s) \
# |> filter(fn: (r) => r._measurement == 'cell_measurements') \
# |> group(columns: ['cell', '_field', 'e2NodeId']) \
# |> mean() \
# |> keep(columns: ['_value', '_field', 'cell', 'e2NodeId'])\" \
# }"