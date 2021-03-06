#!/bin/bash
CONFIG_FILE=$PWD/config/application.properties
PFILES=$PWD/src/main/util.py
SFILES=$PWD/data/taxi_zone_lookup.csv
CASSANDRA=com.datastax.spark:spark-cassandra-connector_2.11:2.3.2
SPARK_BATCH_CLUSTER=ec2-35-171-12-195.compute-1.amazonaws.com
spark-submit --master spark://$SPARK_BATCH_CLUSTER:7077 \
                 --files $SFILES   \
                 --py-files $PFILES \
                 --packages $CASSANDRA \
                 --driver-memory 4G \
                 --executor-memory 4G \
                 src/main/batch_process_stats.py \
                 $CONFIG_FILE prod  

