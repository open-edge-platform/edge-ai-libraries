import requests
import pytest
import time
import os
import subprocess

def get_ip_address():
    result = subprocess.run("hostname -I | awk '{print $1}'", shell=True, capture_output=True, text=True)
    ip_address = result.stdout.strip()
    return ip_address


@pytest.fixture(scope="class")
def check_vllm_model_status():   
    
    model_started = False
    ip = get_ip_address()
    health_url = f"http://{ip}:8080/health"
    print(health_url)
    must_end = time.time() + 50000
    print("Checking health of services.")
    while True and time.time() < must_end:
        try:
            response = requests.get(health_url)     
            print(response.status_code)
            if response.status_code == 200:
                model_started = True
                break
            else:
                print("Checking model server is up..")
                time.sleep(10)
        except requests.exceptions.ConnectionError:
            print(f"Error: Unable to reach {health_url}. The server might be down or there could be a network issue.")
            continue
    yield model_started


@pytest.fixture(scope="class")
def check_ovms_model_status():        
    model_started = False
    ip = get_ip_address()
    completion_url = f"http://{ip}:8300/v3/chat"
    #message = [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": "test"} ]
    message = [{"role": "user", "content": "test"}]
    body = {"model": os.getenv('LLM_MODEL'), "messages": message, "stream": True}
    must_end = time.time() + 50000
    print("Checking ovms server status..")
    print(completion_url)
    while True and time.time() < must_end:
        try:
            response = requests.post(url=completion_url, json=body, stream=True) 
            print(response.status_code)
            if response.status_code == 200:
                model_started = True
                break
            else:
                print("Checking model server is up..")
                time.sleep(10)
        except requests.exceptions.ConnectionError:
            print(f"Error: Unable to reach {completion_url}. The server might be down or there could be a network issue.")
            continue
    yield model_started


@pytest.fixture(scope="class")
def check_chatqna_core_status():   
    ip = get_ip_address()
    model_started = False
    health_url = f"http://{ip}:8888/health"
    print(health_url)
    must_end = time.time() + 50000
    print("Checking health of services.")
    while True and time.time() < must_end:
        try:
            response = requests.get(health_url)     
            print(response.status_code)
            if response.status_code == 200:
                model_started = True
                break
            else:
                print("Checking model server is up..")
                time.sleep(10)
        except requests.exceptions.ConnectionError:
            print(f"Error: Unable to reach {health_url}. The server might be down or there could be a network issue.")
            continue
    yield model_started



@pytest.fixture(scope="class")
def check_chatqna_helm_status():        
    model_started = False
    ip = get_ip_address()
    completion_url = f"http://{ip}:8080/chat"
    body = {"input":"test"}
    must_end = time.time() + 50000
    print("Checking helm server status..")
    print(completion_url)
    while True and time.time() < must_end:
        try:
            response = requests.post(url=completion_url, json=body, stream=True) 
            print(response.status_code)
            if response.status_code == 200:
                model_started = True
                break
            else:
                print("Checking model server is up..")
                time.sleep(10)
        except requests.exceptions.ConnectionError:
            print(f"Error: Unable to reach {completion_url}. The server might be down or there could be a network issue.")
            continue
    yield model_started
