import os
import pytest
from fastapi import HTTPException
import requests


DEVICE = os.getenv("DEVICE", "CPU")
BACKEND_DATAPREP_BASE_URL = os.getenv("BACKEND_DATAPREP_BASE_URL", "http://localhost:9990")
LOCAL_EMBED_MODEL_ID = os.getenv("LOCAL_EMBED_MODEL_ID", "CLIP-ViT-H-14")
DATA_INGEST_WITH_DETECT = os.getenv("DATA_INGEST_WITH_DETECT", "True").lower() == "true"
HOST_DATA_PATH = os.getenv("HOST_DATA_PATH", "/home/user/data")
MOUNT_DATA_PATH = "/home/user/data"
TEST_DATA_PATH = os.path.join(MOUNT_DATA_PATH, "test_data")

def helper_map2host(file_path: str):
    """
    Helper function to map a file path from the container to the host.
    """
    if file_path.startswith(MOUNT_DATA_PATH):
        return file_path.replace(MOUNT_DATA_PATH, HOST_DATA_PATH)
    else:
        return file_path

@pytest.fixture(scope="session", autouse=True)
def download_test_data():
    """
    Fixture to download test data as a pre-step for all tests.
    """
    test_data_url = [
        "https://images.squarespace-cdn.com/content/v1/659e1d627cfb464f89ed5d6d/16cb28f5-86eb-4bdd-a240-fb3316523aee/AdobeStock_663850233.jpeg",
        "http://farm6.staticflickr.com/5268/5602445367_3504763978_z.jpg",
        "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4"
    ]
    
    # Ensure the directory exists
    os.makedirs(TEST_DATA_PATH, exist_ok=True)
    test_files = []

    # Download the test data files if they don't already exist
    for url in test_data_url:
        test_data_file = os.path.join(TEST_DATA_PATH, url.split("/")[-1])
        if not os.path.exists(test_data_file):
            print(f"Downloading test data from {url}...")
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Failed to download test data from {url}")
            with open(test_data_file, "wb") as f:
                f.write(response.content)

        test_files.append(test_data_file)

    yield [helper_map2host(file) for file in test_files]

    # Cleanup after tests
    url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/delete_all"  
    response = requests.delete(url, timeout=10) 
    if os.path.exists(TEST_DATA_PATH):
        import shutil
        shutil.rmtree(TEST_DATA_PATH)

@pytest.fixture(scope="function", autouse=True)
def clear_db():
    url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/delete_all"  
    response = requests.delete(url, timeout=10) 


def test_ingest_host_dir_api(download_test_data):
    url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/ingest"  

    payload = {
        "file_dir": TEST_DATA_PATH,
        "frame_extract_interval": 15,
        "do_detect_and_crop": DATA_INGEST_WITH_DETECT
    }

    result = {}

    response = requests.post(url, json=payload, timeout=10)  

    result = response.json()
    response_text = "\n".join(f"{key}: {value}" for key, value in result.items())
    assert "Files successfully processed" in response_text, "Ingest endpoint did not return expected success message"

    info_url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/info"  
    response = requests.get(info_url, timeout=10)  

    result = response.json()
    assert len(download_test_data) == result["Number of processed files"], "Ingested files count does not match expected value"


def test_ingest_host_dir_api_notexist(download_test_data):
    url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/ingest"  

    payload = {
        "file_dir": os.path.join(TEST_DATA_PATH, "notexist_dir"),
        "frame_extract_interval": 15,
        "do_detect_and_crop": DATA_INGEST_WITH_DETECT
    }

    response = requests.post(url, json=payload, timeout=10)  

    assert response.status_code == 500
    assert "Error" in response.json()["detail"]


def test_ingest_host_file_api(download_test_data):
    url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/ingest"  

    payload = {
        "file_path": download_test_data[0],
        "frame_extract_interval": 15,
        "do_detect_and_crop": DATA_INGEST_WITH_DETECT
    }

    result = {}

    response = requests.post(url, json=payload, timeout=10)  

    result = response.json()
    response_text = "\n".join(f"{key}: {value}" for key, value in result.items())
    assert "Files successfully processed" in response_text, "Ingest endpoint did not return expected success message"

    info_url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/info"  
    response = requests.get(info_url, timeout=10)  

    result = response.json()
    assert 1 == result["Number of processed files"], "Ingested files count does not match expected value"

def test_ingest_host_file_api_notexist(download_test_data):
    url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/ingest"  

    payload = {
        "file_path": os.path.join(TEST_DATA_PATH, "notexist_file.jpg"),
        "frame_extract_interval": 15,
        "do_detect_and_crop": DATA_INGEST_WITH_DETECT
    }

    response = requests.post(url, json=payload, timeout=10)  

    assert response.status_code == 500
    assert "Error" in response.json()["detail"]

def test_ingest_api_wo_detect(download_test_data):
    ingest_url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/ingest"  
    delete_url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/delete"

    payload = {
        "file_path": download_test_data[1],
        "frame_extract_interval": 15,
        "do_detect_and_crop": True
    }

    response = requests.post(ingest_url, json=payload, timeout=10)  
    assert response.status_code == 200

    response = requests.delete(delete_url, params={"file_path": download_test_data[1]}, timeout=10)
    assert response.status_code == 200
    num_with_detect = len(response.json()["removed_ids"])

    payload = {
        "file_path": download_test_data[1],
        "frame_extract_interval": 15,
        "do_detect_and_crop": False
    }

    response = requests.post(ingest_url, json=payload, timeout=10)  
    assert response.status_code == 200

    response = requests.delete(delete_url, params={"file_path": download_test_data[1]}, timeout=10)
    assert response.status_code == 200
    num_wo_detect = len(response.json()["removed_ids"])

    assert num_with_detect > num_wo_detect, "Number of files with detection should be greater than without detection"


def test_get_file_info_api(download_test_data):
    ingest_url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/ingest"  

    payload = {
        "file_dir": TEST_DATA_PATH,
        "frame_extract_interval": 15,
        "do_detect_and_crop": DATA_INGEST_WITH_DETECT
    }

    response = requests.post(ingest_url, json=payload, timeout=10)
    assert response.status_code == 200, "Ingest endpoint failed to process files"

    url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/get"

    for file_path in download_test_data:
        response = requests.get(url, params={"file_path": file_path}, timeout=10)
        assert response.status_code == 200
        assert response.json()["file_path"] == file_path, f"File path mismatch for {file_path}"


def test_delete_file_api(download_test_data):
    ingest_url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/ingest"  

    payload = {
        "file_dir": TEST_DATA_PATH,
        "frame_extract_interval": 15,
        "do_detect_and_crop": DATA_INGEST_WITH_DETECT
    }

    response = requests.post(ingest_url, json=payload, timeout=10)
    result = response.json()
    response_text = "\n".join(f"{key}: {value}" for key, value in result.items())
    assert response.status_code == 200, "Ingest endpoint failed to process files"

    url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/delete"

    for file_path in download_test_data:
        response = requests.delete(url, params={"file_path": file_path}, timeout=10)
        assert response.status_code == 200
        for ids in response.json()["removed_ids"]:
            assert str(ids) in response_text, f"File ID {ids} not found in response text after deletion for {file_path}"

def test_clear_db_api(download_test_data):
    ingest_url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/ingest"  

    payload = {
        "file_dir": TEST_DATA_PATH,
        "frame_extract_interval": 15,
        "do_detect_and_crop": DATA_INGEST_WITH_DETECT
    }

    response = requests.post(ingest_url, json=payload, timeout=10)
    assert response.status_code == 200, "Ingest endpoint failed to process files"
    
    url = f"{BACKEND_DATAPREP_BASE_URL}/v1/dataprep/delete_all"
    response = requests.delete(url, timeout=10)
    assert response.status_code == 200, "Failed to clear the database"