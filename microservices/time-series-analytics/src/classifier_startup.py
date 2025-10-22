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
import socket
import logging
import shutil
import select
import threading
import tomlkit
from influxdb import InfluxDBClient

TEMP_KAPACITOR_DIR = tempfile.gettempdir()
KAPACITOR_DEV = "kapacitor_devmode.conf"
KAPACITOR_PROD = "kapacitor.conf"
SUCCESS = 0
FAILURE = -1
KAPACITOR_PORT = 9092
KAPACITOR_NAME = 'kapacitord'

def kapacitor_daemon_logs(logger):
    """Read the kapacitor logs and print it to stdout
    """
    kapacitor_log_file = "/tmp/log/kapacitor/kapacitor.log"
    while True:
        if os.path.isfile(kapacitor_log_file):
            break
        else:
            time.sleep(1)
    f = subprocess.Popen(['tail','-F',kapacitor_log_file],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
        self.kapacitor_proc = None

    def write_cert(self, file_name, cert):
        """Write certificate to given file path"""
        try:
            shutil.copy(cert, file_name)
            os.chmod(file_name, 0o400)
        except (OSError, IOError) as err:
            self.logger.debug("Failed creating file: %s, Error: %s ", file_name, err)

    def check_udf_package(self, config, dir_name):
        """ Check if UDF deployment package is present in the container
        """
        logger.info("Checking if UDF deployment package is present in the container...")
        path = "/tmp/" + dir_name + "/"
        udf_dir = os.path.join(path, "udfs")
        model_dir = os.path.join(path, "models")
        tick_scripts_dir = os.path.join(path, "tick_scripts")
        found_udf = False
        found_tick_scripts = False
        found_model = False
        udf_name = config["udfs"]["name"]


        if not os.path.isdir(path):
            self.logger.error(
                "UDF deployment package directory %s does not exist. "
                "Please check and upload/copy the UDF deployment package.",
                udf_name
            )
            return False
        if os.path.isdir(udf_dir) and os.path.isfile(os.path.join(udf_dir,
                                                                  config['udfs']["name"] + ".py")):
            found_udf = True

        tick_script_path = os.path.join(tick_scripts_dir, config['udfs']["name"] + ".tick")
        if os.path.isdir(tick_scripts_dir) and os.path.isfile(tick_script_path):
            found_tick_scripts = True

        # model file is optional
        if "models" in config["udfs"].keys():
            if os.path.isdir(model_dir):
                for fname in os.listdir(model_dir):
                    if fname.startswith(config['udfs']["name"]):
                        found_model = True
                        break
        else:
            found_model = True
        if not (found_model and found_udf and found_tick_scripts):
            missing_items = []
            if not found_model:
                missing_items.append(f"model file for task {config['udfs']['name']}")
                self.logger.warning("Missing model")
            if not found_udf:
                missing_items.append(f"udf file for task {config['udfs']['name']}")
                self.logger.warning("Missing udf")
            if not found_tick_scripts:
                missing_items.append(f"tick script for task {config['udfs']['name']}")
                self.logger.warning("Missing tick script")
            self.logger.error(
                "Missing " + ", ".join(missing_items) + 
                ". Please check and upload/copy the UDF deployment package."
            )
            return False
        else:
            self.logger.info("UDF deployment package %s exists.", path)
            return True

    def install_udf_package(self, dir_name):
        """ Install python package from udf/requirements.txt if exists
        """

        python_package_requirement_file = "/tmp/" + dir_name + "/udfs/requirements.txt"
        python_package_installation_path = "/tmp/py_package"
        status = subprocess.run(["mkdir", "-p", python_package_installation_path], check=False)
        if status.returncode != SUCCESS:
            self.logger.error("Failed to create directory %s for installing python packages.",
                              python_package_installation_path)
            return False
        if os.path.isfile(python_package_requirement_file):
            status = subprocess.run([
                "pip3", "install", "-r", python_package_requirement_file,
                "--target", python_package_installation_path
            ], check=False)
            if status.returncode != SUCCESS:
                self.logger.error("Failed to install python packages from %s",
                                  python_package_requirement_file)
                return False

    def start_kapacitor(self,
                        kapacitor_url_hostname,
                        secure_mode):
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

            self.kapacitor_proc = subprocess.Popen(
                ["kapacitord", "-hostname", kapacitor_url_hostname, "-config", kapacitor_conf]
            )

            # Start a thread to reap the kapacitor process when it exits
            def reap_kapacitor_proc(proc, logger):
                try:
                    proc.wait()
                    logger.info("Kapacitor daemon process has exited and was reaped.")
                except (subprocess.SubprocessError, OSError) as e:
                    logger.error("Error while reaping kapacitor process: %s", e)
            threading.Thread(target=reap_kapacitor_proc, args=(self.kapacitor_proc, self.logger),
                                    daemon=True).start()
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

    def enable_classifier_task(
            self,
            host_name,
            tick_script,
            dir_name,
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

        path = "/tmp/" + dir_name + "/tick_scripts/"
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
        if 'udfs' not in config.keys():
            error_msg = "udfs key is missing in config, EXITING!!!"
            return error_msg, FAILURE
        return None, SUCCESS

    def enable_tasks(self, config, kapacitor_started, kapacitor_url_hostname, dir_name):
        """Starting the task based on the config
           read from the etcd
        """
        if 'name' in config['udfs']:
            tick_script = config['udfs']['name'] + ".tick"
        else:
            error_msg = ("UDF name key is missing in config "
                            "Please provide the UDF name to run "
                            "EXITING!!!!")
            return error_msg, FAILURE

        task_name = config['udfs']['name']

        if kapacitor_started:
            self.logger.info("Enabling %s", tick_script)
            self.enable_classifier_task(kapacitor_url_hostname,
                                        tick_script,
                                        dir_name,
                                        task_name)
        while True:
            time.sleep(1)


log_level = os.getenv('KAPACITOR_LOGGING_LEVEL', 'INFO').upper()
logging_level = getattr(logging, log_level, logging.INFO)

# Configure logging
logging.basicConfig(
    level=logging_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
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
            client = InfluxDBClient(
                host=influx_host,
                port=8086,
                username=influx_username,
                password=influx_password,
                ssl=True,
                database=influx_db
            )
        else:
            client = InfluxDBClient(
                host=influx_host,
                port=8086,
                username=influx_username,
                password=influx_password,
                database=influx_db
            )

        # Query to list subscriptions
        query = 'SHOW SUBSCRIPTIONS'

        try:
            results = client.query(query)
            subscriptions = list(results.get_points())
            # Print the subscriptions
            for subscription in subscriptions:
                if subscription['name'].startswith("kapacitor-"):
                    logger.debug("Retention Policy: %s, Name: %s, Mode: %s, Destinations: %s",
                                  subscription['retention_policy'],
                                  subscription['name'],
                                  subscription['mode'],
                                  subscription['destinations']
                    )
                    drop_query = "DROP SUBSCRIPTION \""+subscription['name']+"\" ON "+ influx_db+".autogen"
                    logger.info("Deleting subscription: %s", subscription['name'])
                    client.query(drop_query)
        except Exception as e:
            print("Failed to list subscriptions: %s", e)

        # Close the connection
        client.close()
    except Exception as e:
        logger.exception("Deleting old subscription failed, Error: %s", e)

def classifier_startup(config):
    """Main to start kapacitor service
    """
    mode = os.getenv("SECURE_MODE", "false")
    secure_mode = mode.lower() == "true"

    # Delete old subscription
    if os.environ["KAPACITOR_INFLUXDB_0_URLS_0"] != "":
        delete_old_subscription(secure_mode)
    conf_file = KAPACITOR_PROD if secure_mode else KAPACITOR_DEV
    # Copy the kapacitor conf file to the /tmp directory
    shutil.copy("/app/config/" + conf_file, "/tmp/" + conf_file)
    # Read the existing configuration
    with open("/tmp/" + conf_file, 'r', encoding='utf-8') as file:
        config_data = tomlkit.parse(file.read())
    udf_name = config['udfs']['name']
    if "models" in config['udfs'].keys():
        model_name = config['udfs']['models']
    else:
        model_name = ""
    device = "auto"
    device_config = config['udfs'].get("device", None)
    if device_config:
        device = device_config.lower()
        if device == "cpu":
            device = "auto"
        elif device == "gpu" or (device.startswith("gpu:") and device.split(":")[1].isdigit()):
            device = device
        else:
            raise ValueError(f"Invalid value for 'device' in udfs: {device_config}, must be 'cpu' or 'gpu'")

    if os.getenv("SAMPLE_APP") is not None:
        dir_name = os.getenv("SAMPLE_APP")
    else:
        dir_name = udf_name

    udf_section = config_data.get('udf', {}).get('functions', {})
    udf_section[udf_name] = tomlkit.table()

    udf_section[udf_name]['prog'] = 'python3'

    udf_section[udf_name]['args'] = ["-u", "/tmp/"+ dir_name +"/udfs/" + udf_name + ".py"]

    udf_section[udf_name]['timeout'] = "60s"
    udf_section[udf_name]['env'] = {
        'PYTHONPATH': "/tmp/py_package:/app/kapacitor_python/:",
        'MODEL_PATH': os.path.join("/tmp", dir_name, "models", model_name),
        'DEVICE': device
    }
    if "alerts" in config.keys() and "mqtt" in config["alerts"].keys():
        config_data["mqtt"][0]["name"] = config["alerts"]["mqtt"]["name"]
        mqtt_url = config_data["mqtt"][0]["url"]
        mqtt_url = mqtt_url.replace("MQTT_BROKER_HOST",
                                    config["alerts"]["mqtt"]["mqtt_broker_host"])
        mqtt_url = mqtt_url.replace("MQTT_BROKER_PORT",
                                    str(config["alerts"]["mqtt"]["mqtt_broker_port"]))
        config_data["mqtt"][0]["url"] = mqtt_url
    else:
        config_data["mqtt"][0]["enabled"] = False

    if os.environ["KAPACITOR_INFLUXDB_0_URLS_0"] != "":
        config_data["influxdb"][0]["enabled"] = True
    # Write the updated configuration back to the file
    with open("/tmp/" + conf_file, 'w', encoding='utf-8') as file:
        file.write(tomlkit.dumps(config_data, sort_keys=False))

    # Copy the /app/temperature_Classifier folder to /tmp/temperature_classifier
    src_dir = "/app/temperature_classifier"
    dst_dir = "/tmp/temperature_classifier"
    if os.path.exists(dst_dir):
        shutil.rmtree(dst_dir)
    shutil.copytree(src_dir, dst_dir)

    logger.info("=============== STARTING kapacitor ==============")
    host_name = "localhost"
    if not host_name:
        error_log = ('Kapacitor hostname is not Set in the container. '
                     'So exiting...')
        kapacitor_classifier.exit_with_failure_message(error_log)

    msg, status = kapacitor_classifier.check_config(config)
    if status is FAILURE:
        kapacitor_classifier.exit_with_failure_message(msg)


    status = kapacitor_classifier.check_udf_package(config, dir_name)
    if status is False:
        error_log = ("UDF deployment package is not present in the container. "
                    "Please check the UDF deployment package and try again. ")
        logger.error(error_log)
        return FAILURE
    kapacitor_classifier.install_udf_package(dir_name)
    kapacitor_started = False


    kapacitor_url_hostname = (os.environ["KAPACITOR_URL"].split("://")[1]).split(":")[0]
    if(kapacitor_classifier.start_kapacitor(kapacitor_url_hostname,
                                            secure_mode) is True):
        kapacitor_started = True
    else:
        error_log = "Kapacitor is not starting. So Exiting..."
        kapacitor_classifier.exit_with_failure_message(error_log)


    msg, status = kapacitor_classifier.enable_tasks(config,
                                                    kapacitor_started,
                                                    kapacitor_url_hostname,
                                                    dir_name)
    if status is FAILURE:
        kapacitor_classifier.exit_with_failure_message(msg)

kapacitor_classifier = KapacitorClassifier(logger)

t1 = threading.Thread(target=kapacitor_daemon_logs, args=[logger])
t1.daemon = True
t1.start()
