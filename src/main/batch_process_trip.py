"""
This main program loads the taxi trip historical data, extracts relevant fields and computes
values required for generating metrics.

The input file consists of the following format
VendorID,tpep_pickup_datetime,tpep_dropoff_datetime,passenger_count,trip_distance,
RatecodeID,store_and_fwd_flag,PULocationID,DOLocationID,payment_type,fare_amount,
extra,mta_tax,tip_amount,tolls_amount,improvement_surcharge,total_amount

Fields extracted mainly are - tpep_pickup_datetime,PULocationID (indexes 1, 7)

Performs transformations and actions on Spark RDD to obtain the following fields

assign_date(only date)
borough name (lookup using pick up location)
time block (computed out of the time component in the above original field)
number of trips per time block (unit time block is 15 mins. 24hours will have 96 time blocks)

"""
import pyspark
from pyspark import SparkConf, SparkContext, SQLContext
from pyspark.sql import SparkSession
import sys
from cassandra.cluster import Cluster
import util

class TaxiBatch:
    """
    This class entirely processes the batch data with help of util functions.
    It reads the settings from application.properties file, process the records line
    by line with categorization by timeblock, day, month, and borough.

    It does a series of transformations and finally saves it into the database
    """

    def process_batch_data(self):
        """
        This function processes batch dataset. It loads the raw data from s3
        and does a series of transformations, computations by key
        """
        #load raw files using spark context
        self.data_stats = self.sc.textFile(self.s3_url)

        #map and get total trips in one timeblock using
        #reducebykey time block, day, month, borough
        #aggregateByKey using the same fields above to get (count of matching records,sum of trips)
        zone_info_bc = self.sc.broadcast(self.zone_info)
        self.data_stats = self.data_stats.map(lambda row : util.process_trip_record(row, zone_info_bc.value)) \
                     .filter(lambda row: row != None) \
                     .map(lambda row : ((row[0].split(" ")[0],row[1],row[2],row[3], row[4], row[5]),1)) \
                     .reduceByKey(lambda x,y : x+y) \
                     .map(lambda x : ((x[0][1],x[0][2],x[0][3],x[0][4],x[0][5]),x[1])) \
                     .aggregateByKey((0,0),lambda x,y : (x[0]+1, x[1]+y), lambda x,y: (x[0]+y[0],x[1]+y[1])) \
                     .map(lambda x : (x[0][0],x[0][1],x[0][2],x[0][3],x[0][4],x[1][1]/x[1][0]))

    def save_batch_trip_stats(self):
        """
        This function saves the batch processing results into the database
        """
        spark = SparkSession(self.sc)
        hasattr(self.data_stats, "toDF")
        self.data_stats.toDF(schema=["time_block","month","day","borough_code","borough_name","mean"]).write.format("org.apache.spark.sql.cassandra").mode("append").options(table=self.cassandra_table, keyspace=self.cassandra_keyspace).save()
        print ("Saved data successfully")

    def __init__(self,env,config_file):
        """
        This initializes the class and loads the properties from the
        application.properties file. It initiates the SparkContext and
        loads the borough coordinates for nyc
        """
        #load all the properties
        self.properties = util.load_application_properties(env, config_file)
        self.cassandra_server = self.properties["cassandra.host.name"]
        self.cassandra_table = self.properties["cassandra.trip_stats_table"]
        self.cassandra_keyspace = self.properties["cassandra.trip.keyspace"]
        self.spark_master = self.properties["spark.master"]
        self.s3_url=self.properties["batch_s3_url"]
        self.nyc_borough = self.properties["nyc_borough"]
        self.nyc_zones=self.properties["nyc_zones"]

        #initialize SparkConf and SparkContext along  with cassandra settings
        self.conf = SparkConf().setAppName("trip").set("spark.cassandra.connection.host",self.cassandra_server)
        self.sc = SparkContext(conf=self.conf)

        #load the nyc borough coordinates from geojson file
        self.zone_info = util.get_zone_dict(self.nyc_zones)


"""
The main method to process historical trip data. This instantiates the class
TaxiBatch and process the batch data and saves it to the database
"""
if __name__ == '__main__':

    #check for proper arguments
    if len(sys.argv) != 3:
        sys.stderr.write("Please check the command line options and arguments")
        sys.exit(-1)

    #application.properties filename
    config_file= sys.argv[1]
    #section in the properties filename
    env = sys.argv[2]

    #instantiate the batch processing class
    taxi_batch = TaxiBatch(env, config_file)

    try:
        #initiate batch processing
        taxi_batch.process_batch_data()
        #saving results to the database
        taxi_batch.save_batch_trip_stats()
    except Exception as e:
        print "Error processing the trip batch data", e
        sys.exit(-1)

