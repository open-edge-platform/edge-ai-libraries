#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""Kapacitor service
"""

import subprocess
import os
import os.path
import time
import tempfile
import sys
import json
import socket
import shlex
import logging
import shutil
from threading import Thread
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import tomlkit
import select
import threading
import os.path
import threading
from influxdb import InfluxDBClient
from mr_interface import MRHandler

TEMP_KAPACITOR_DIR = tempfile.gettempdir()
KAPACITOR_DEV = "kapacitor_devmode.conf"
KAPACITOR_PROD = "kapacitor.conf"
SUCCESS = 0
FAILURE = -1
KAPACITOR_PORT = 9092
KAPACITOR_NAME = 'kapacitord'
CONFIG_KEY_PATH = 'config'
CONFIG_FILE = "/app/config.json"

logging.getLogger("watchdog.observers.inotify_buffer").setLevel(logging.WARNING)
mrHandlerObj = None
class ConfigFileEventHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith("config.json"):
            logger.info(f"{event.src_path} file has been modified. Exiting to restart container...")
            os._exit(1)

def KapacitorDaemonLogs(logger):
    kapacitor_log_file = "/tmp/log/kapacitor/kapacitor.log"
    while True:
        if os.path.isfile(kapacitor_log_file):
            break
        else:
            time.sleep(1)
    f = subprocess.Popen(['tail','-F',kapacitor_log_file],\
                                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    p = select.poll()
    p.register(f.stdout)
    while True:
        if p.poll(1):
            logger.info(f.stdout.readline())
        else:
            time.sleep(1)
class KapacitorClassifier():
    """Kapacitor Classifier have all the methods related to
       starting kapacitor, udf and tasks
    """
    def __init__(self, logger):
        self.logger = logger

    def write_cert(self, file_name, cert):
        """Write certificate to given file path
        """
        try:
            shutil.copy(cert, file_name)
            os.chmod(file_name, 0o400)
        except (OSError, IOError) as err:
            self.logger.debug("Failed creating file: {}, Error: {} ".format(
                file_name, err))
    
    def check_udf_package(self, config):
        """ Check if udf package is present in the container
        """
        logger.info("Checking if UDF package is present in the container...")
        path = "/tmp/" + config['task']["task_name"] +"/"
        udf_dir = os.path.join(path, "udfs") 
        model_dir = os.path.join(path, "models") 
        tick_scripts_dir = os.path.join(path, "tick_scripts") 
        found_udf = False
        found_tick_scripts = False
        found_model = False
        while True:
            if os.path.isdir(udf_dir) and os.path.isfile(os.path.join(udf_dir, config['task']["task_name"] + ".py")):
                found_udf = True
        
            if os.path.isdir(tick_scripts_dir) and os.path.isfile(os.path.join(tick_scripts_dir, config['task']["task_name"] + ".tick")):
                found_tick_scripts = True

            # Check for any file with the task_name in the models directory, regardless of extension
            if "models" in config["task"]["udfs"].keys():
                if os.path.isdir(model_dir):
                    for fname in os.listdir(model_dir):
                        if fname.startswith(config['task']["task_name"]):
                            found_model = True
                            break
            else:
                found_model = True
            if not(found_model and found_udf and found_tick_scripts):
                missing_items = []
                if not found_model:
                    missing_items.append(f"model file for task {mrHandlerObj.tasks['task_name']}")
                if not found_udf:
                    missing_items.append(f"udf file for task {mrHandlerObj.tasks['task_name']}")
                if not found_tick_scripts:
                    missing_items.append(f"tick script for task {mrHandlerObj.tasks['task_name']}")
                self.logger.error(
                    "Missing " + ", ".join(missing_items) + ". Please check and upload/copy the udf package."
                )
            else:
                return
            time.sleep(5)

    def install_udf_package(self,config):
        """ Install python package from udf/requirements.txt if exists
        """

        python_package_requirement_file = "/tmp/" + config['task']["task_name"] + "/udfs/requirements.txt"
        python_package_installation_path = "/tmp/py_package"
        os.system(f"mkdir -p {python_package_installation_path}")
        if os.path.isfile(python_package_requirement_file):
            os.system(f"pip3 install -r {python_package_requirement_file} --target {python_package_installation_path}")

    def start_kapacitor(self,
                        config,
                        kapacitor_url_hostname,
                        secure_mode,
                        app_name):
        """Starts the kapacitor Daemon in the background
        """
        http_scheme = "http://"
        https_scheme = "https://"
        kapacitor_port = os.environ["KAPACITOR_URL"].split("://")[1]
        if os.environ["KAPACITOR_INFLUXDB_0_URLS_0"] != "":
            influxdb_hostname_port = os.environ[
                "KAPACITOR_INFLUXDB_0_URLS_0"].split("://")[1]

        try:
            if secure_mode:
                # Populate the certificates for kapacitor server
                kapacitor_conf = '/tmp/' + KAPACITOR_PROD

                os.environ["KAPACITOR_URL"] = "{}{}".format(https_scheme,
                                                            kapacitor_port)
                os.environ["KAPACITOR_UNSAFE_SSL"] = "false"
                if os.environ["KAPACITOR_INFLUXDB_0_URLS_0"] != "":
                    os.environ["KAPACITOR_INFLUXDB_0_URLS_0"] = "{}{}".format(
                        https_scheme, influxdb_hostname_port)
            else:
                kapacitor_conf = '/tmp/' + KAPACITOR_DEV
                os.environ["KAPACITOR_URL"] = "{}{}".format(http_scheme,
                                                            kapacitor_port)
                os.environ["KAPACITOR_UNSAFE_SSL"] = "true"
                if os.environ["KAPACITOR_INFLUXDB_0_URLS_0"] != "":
                    os.environ["KAPACITOR_INFLUXDB_0_URLS_0"] = "{}{}".format(
                        http_scheme, influxdb_hostname_port)

            subprocess.Popen(["kapacitord", "-hostname", kapacitor_url_hostname,
                              "-config", kapacitor_conf, "&"])
            self.logger.info("Started kapacitor Successfully...")
            return True
        except subprocess.CalledProcessError as err:
            self.logger.info("Exception Occured in Starting the Kapacitor " +
                             str(err))
            return False

    def process_zombie(self, process_name):
        """Checks the given process is Zombie State & returns True or False
        """
        try:
            out1 = subprocess.run(["ps", "-eaf"], stdout=subprocess.PIPE,
                                  check=False)
            out2 = subprocess.run(["grep", process_name], input=out1.stdout,
                                  stdout=subprocess.PIPE, check=False)
            out3 = subprocess.run(["grep", "-v", "grep"], input=out2.stdout,
                                  stdout=subprocess.PIPE, check=False)
            out4 = subprocess.run(["grep", "defunct"], input=out3.stdout,
                                  stdout=subprocess.PIPE, check=False)
            out = subprocess.run(["wc", "-l"], input=out4.stdout,
                                 stdout=subprocess.PIPE, check=False)
            out = out.stdout.decode('utf-8').rstrip("\n")

            if out == b'1':
                return True
            return False
        except subprocess.CalledProcessError as err:
            self.logger.info("Exception Occured in Starting Kapacitor " +
                             str(err))

    def kapacitor_port_open(self, host_name):
        """Verify Kapacitor's port is ready for accepting connection
        """
        if self.process_zombie(KAPACITOR_NAME):
            self.exit_with_failure_message("Kapacitor fail to start. "
                                           "Please verify the "
                                           "Time Series Analytics microservice logs for "
                                           "UDF/kapacitor Errors.")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.logger.info("Attempting to connect to Kapacitor on port 9092")
        result = sock.connect_ex((host_name, KAPACITOR_PORT))
        self.logger.info("Attempted  Kapacitor on port 9092 : Result " +
                         str(result))
        if result == SUCCESS:
            self.logger.info("Successful in connecting to Kapacitor on"
                             "port 9092")
            return True

        return False

    def exit_with_failure_message(self, message):
        """Exit the container with failure message
        """
        if message:
            self.logger.error(message)
        sys.exit(FAILURE)

    def enable_classifier_task(self,
                               host_name,
                               tick_script,
                               task_name):
        """Enable the classifier TICK Script using the kapacitor CLI
        """
        retry_count = 5
        retry = 0
        kap_connectivity_retry = 10
        kap_retry = 0
        while not self.kapacitor_port_open(host_name):
            time.sleep(5)
            kap_retry = kap_retry + 1
            if kap_retry > kap_connectivity_retry:
                self.logger.error("Error connecting to Kapacitor Daemon... Restarting Kapacitor...")
                os._exit(1)

        self.logger.info("Kapacitor Port is Open for Communication....")
 
        path = "/tmp/" + task_name + "/tick_scripts/"
        while retry < retry_count:
            define_pointcl_cmd = ["kapacitor", "-skipVerify", "define",
                                  task_name, "-tick",
                                  path + tick_script]

            if subprocess.check_call(define_pointcl_cmd) == SUCCESS:
                define_pointcl_cmd = ["kapacitor", "-skipVerify", "enable",
                                      task_name]
                if subprocess.check_call(define_pointcl_cmd) == SUCCESS:
                    self.logger.info("Kapacitor Tasks Enabled Successfully")
                    self.logger.info("Kapacitor Initialized Successfully. "
                                     "Ready to Receive the Data....")
                    break

                self.logger.info("ERROR:Cannot Communicate to Kapacitor.")
            else:
                self.logger.info("ERROR:Cannot Communicate to Kapacitor. ")
            self.logger.info("Retrying Kapacitor Connection")
            time.sleep(0.0001)
            retry = retry + 1

    def check_config(self, config):
        """Starting the udf based on the config
           read from the etcd
        """
        # Checking if udf present in task and
        # run it based on etcd config
        if 'task' not in config.keys():
            error_msg = "task key is missing in config, EXITING!!!"
            return error_msg, FAILURE
        return None, SUCCESS

    def enable_tasks(self, config, kapacitor_started, kapacitor_url_hostname, secure_mode):
        """Starting the task based on the config
           read from the etcd
        """
        task = config['task']
        if 'tick_script' in task:
            tick_script = task['tick_script']
        else:
            error_msg = ("tick_script key is missing in config "
                            "Please provide the tick script to run "
                            "EXITING!!!!")
            return error_msg, FAILURE

        if 'task_name' in task:
            task_name = task['task_name']
        else:
            error_msg = ("task_name key is missing in config "
                            "Please provide the task name "
                            "EXITING!!!")
            return error_msg, FAILURE

        if kapacitor_started:
            self.logger.info("Enabling {0}".format(tick_script))
            self.enable_classifier_task(kapacitor_url_hostname,
                                        tick_script,
                                        task_name)

        while True:
            time.sleep(1)


def config_file_watch(observer, CONFIG_FILE):
    logger.info(f"Monitoring {CONFIG_FILE} for config changes...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

log_level = os.getenv('KAPACITOR_LOGGING_LEVEL', 'INFO').upper()
logging_level = getattr(logging, log_level, logging.INFO)

# Configure logging
logging.basicConfig(
    level=logging_level,  # Set the log level to DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Log format
)

logger = logging.getLogger(__name__)

def delete_old_subscription(secure_mode):
    """Delete old subscription in influxdb
    """
    try:
        # Connect to InfluxDB
        influx_host = os.getenv('INFLUX_SERVER')
        influx_username = os.getenv('KAPACITOR_INFLUXDB_0_USERNAME')
        influx_password = os.getenv('KAPACITOR_INFLUXDB_0_PASSWORD')
        influx_db = os.getenv('INFLUXDB_DBNAME')
        if secure_mode:
            client = InfluxDBClient(host=influx_host, port=8086, username=influx_username, password=influx_password,ssl=True, database=influx_db)
        else:
            client = InfluxDBClient(host=influx_host, port=8086, username=influx_username, password=influx_password, database=influx_db)

        # Query to list subscriptions
        query = 'SHOW SUBSCRIPTIONS'

        try:
            results = client.query(query)
            subscriptions = list(results.get_points())            
            # Print the subscriptions
            for subscription in subscriptions:
                if subscription['name'].startswith("kapacitor-"):
                    logger.debug(f"Retention Policy: {subscription['retention_policy']}, Name: {subscription['name']}, Mode: {subscription['mode']}, Destinations: {subscription['destinations']}")
                    drop_query = "DROP SUBSCRIPTION \""+subscription['name']+"\" ON "+ influx_db+".autogen"
                    logger.info(f"Deleting subscription: {subscription['name']}")
                    client.query(drop_query)
        except Exception as e:
            print(f"Failed to list subscriptions: {e}")

        # Close the connection
        client.close()
    except Exception as e:
        logger.exception("Deleting old subscription failed, Error: {}".format(e))

def main():
    """Main to start kapacitor service
    """
    try:
        with open (CONFIG_FILE, 'r') as file:
            app_cfg = json.load(file)
        mode = os.getenv("SECURE_MODE", "false")
        secure_mode = mode.lower() == "true"

        config = app_cfg["config"]
        app_name = os.getenv("Appname", "Kapacitor")
    except Exception as e:
        logger.exception("Fetching app configuration failed, Error: {}".format(e))
        os._exit(1)
    global mrHandlerObj
    mrHandlerObj = MRHandler(config, logger)
    event_handler = ConfigFileEventHandler()
    observer = Observer()
    observer.schedule(event_handler, path=CONFIG_FILE, recursive=False)
    observer.start()
    watch_config_change = Thread(target=config_file_watch, args=(observer,CONFIG_FILE,))
    watch_config_change.start()

    # Delete old subscription
    if os.environ["KAPACITOR_INFLUXDB_0_URLS_0"] != "":
        delete_old_subscription(secure_mode)
    conf_file = KAPACITOR_PROD if secure_mode else KAPACITOR_DEV
    # Copy the kapacitor conf file to the /tmp directory
    shutil.copy("/app/config/" + conf_file, "/tmp/" + conf_file)
    # Read the existing configuration
    with open("/tmp/" + conf_file, 'r') as file:
        config_data = tomlkit.parse(file.read())
    udf_name = config['task']['udfs']['name']
    dir_name = udf_name
    if mrHandlerObj is not None and mrHandlerObj.fetch_from_model_registry:
        dir_name = mrHandlerObj.unique_id
    udf_section = config_data.get('udf', {}).get('functions', {})
    udf_section[udf_name] = tomlkit.table()

    udf_section[udf_name]['prog'] = 'python3'
    
    udf_section[udf_name]['args'] = ["-u", "/tmp/"+ dir_name +"/udfs/" + udf_name + ".py"]
    
    udf_section[udf_name]['timeout'] = "60s"
    udf_section[udf_name]['env'] = {
        'PYTHONPATH': "/tmp/py_package:/app/kapacitor_python/:"
    }
    if "alerts" in config.keys() and "mqtt" in config["alerts"].keys():
        config_data["mqtt"][0]["name"] = config["alerts"]["mqtt"]["name"]
        mqtt_url = config_data["mqtt"][0]["url"]
        mqtt_url = mqtt_url.replace("MQTT_BROKER_HOST", config["alerts"]["mqtt"]["mqtt_broker_host"])
        mqtt_url = mqtt_url.replace("MQTT_BROKER_PORT", str(config["alerts"]["mqtt"]["mqtt_broker_port"]))
        config_data["mqtt"][0]["url"] = mqtt_url
    else:
        config_data["mqtt"][0]["enabled"] = False
    
    if os.environ["KAPACITOR_INFLUXDB_0_URLS_0"] != "":
        config_data["influxdb"][0]["enabled"] = True
    # Write the updated configuration back to the file
    with open("/tmp/" + conf_file, 'w') as file:
        file.write(tomlkit.dumps(config_data, sort_keys=False))

    # Copy the /app/temperature_Classifier folder to /tmp/temperature_classifier
    src_dir = "/app/temperature_classifier"
    dst_dir = "/tmp/temperature_classifier"
    if os.path.exists(dst_dir):
        shutil.rmtree(dst_dir)
    shutil.copytree(src_dir, dst_dir)

    kapacitor_classifier = KapacitorClassifier(logger)

    logger.info("=============== STARTING kapacitor ==============")
    host_name = "localhost"
    if not host_name:
        error_log = ('Kapacitor hostname is not Set in the container. '
                     'So exiting...')
        kapacitor_classifier.exit_with_failure_message(error_log)

    msg, status = kapacitor_classifier.check_config(config)
    if status is FAILURE:
        kapacitor_classifier.exit_with_failure_message(msg)

    kapacitor_classifier.check_udf_package(config)
    kapacitor_classifier.install_udf_package(config)
    kapacitor_started = False

    if "alerts" in config.keys() and "opcua" in config["alerts"].keys():
        command = [
                    "uvicorn",
                    "opcua_alerts:app",
                    "--host", "0.0.0.0",
                    "--port", "5000",
                    "--workers", "5",
                    "--no-access-log"
                ]
        def start_fastapi_with_workers():
            # Use subprocess to start Uvicorn with multiple workers
            if secure_mode:
                command.extend([
                    "--ssl-keyfile=/run/secrets/time_series_analytics_microservice_Server_server_key.pem",
                    "--ssl-certfile=/run/secrets/time_series_analytics_microservice_Server_server_certificate.pem"
                ])
            subprocess.run(command)

        try:
            # Start the FastAPI server with workers in a separate thread
            fastapi_thread = threading.Thread(target=start_fastapi_with_workers)
            fastapi_thread.start()
        except Exception as e:
            logger.error(f"Failed to start command '{command}': {e}")


    t1 = threading.Thread(target=KapacitorDaemonLogs, args=[logger])
    t1.start()
    kapacitor_url_hostname = (os.environ["KAPACITOR_URL"].split("://")[1]).split(":")[0]
    if(kapacitor_classifier.start_kapacitor(config,
                                            kapacitor_url_hostname,
                                            secure_mode,
                                            app_name) is True):
        kapacitor_started = True
    else:
        error_log = "Kapacitor is not starting. So Exiting..."
        kapacitor_classifier.exit_with_failure_message(error_log)

    msg, status = kapacitor_classifier.enable_tasks(config,
                                                    kapacitor_started,
                                                    kapacitor_url_hostname,
                                                    secure_mode)
    if status is FAILURE:
        kapacitor_classifier.exit_with_failure_message(msg)


if __name__ == '__main__':
    main()
