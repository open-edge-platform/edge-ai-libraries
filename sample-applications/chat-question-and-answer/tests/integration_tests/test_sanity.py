import requests
import pytest
import time
import json
import os
import subprocess
       
class TestSanity:

    def get_ip_address():
        result = subprocess.run("hostname -I | awk '{print $1}'", shell=True, capture_output=True, text=True)
        ip_address = result.stdout.strip()
        return ip_address

    # Configurations
    HOST = get_ip_address()
    DOCUMENT_URL = f"http://{HOST}:8000/documents"
    STEAM_LOG_URL = f"http://{HOST}:8100/chat"
    DATA_STORE_URL = f"http://{HOST}:8200/data"

    HELM_CHAT = f"http://{HOST}:8080/chat"
    HELM_DATA_STORE_URL = f"http://{HOST}:8005/data"

    # Testdata
    FILEPATHS = ["tests/integration_tests/GenAi.txt"]
    FILENAME = ["GenAi.txt"]
    PAYLOAD = {"input":"what are Generative AI tools?"}
    EXP_ANSWER = "task"
    DELETE_DOC_PARAMS = {"bucket_name": "intel.gai.ragfiles", "delete_all": "true"}
    DATA_STORE_PARAMS = {"bucket_name": "intel.gai.ragfiles", "dest_file_name": "test"}
    
    
    # Common functions
    def make_request(self, url, method, request_payload={}, stream=False, params= {}, files= None):
        response = {}
        headers = {'Content-Type': 'application/json'}
        proxy = {'http': os.environ.get("http_proxy"), 'https': os.environ.get("https_proxy")}
        try:
            response = requests.request(method, url, headers=headers, data=request_payload, proxies=proxy, verify=False, stream=stream, params=params, files=files)                    
        except Exception as e:
            print(f"Request fails with error {e}")
        return response

    def upload_file(self, url, filepaths, filename, params={}, files='files'):
        upload_response, upload_files = {}, []
        try:
            for i in range(len(filepaths)):
                upload_files.append((files, (filename[i], open(filepaths[i], 'r'), 'text/plain')))
            upload_response = requests.request(url=url, method="POST", params=params, files=upload_files)
        except Exception as e:
            print(f"Upload file failed with exception, {e}")
        return upload_response

    def get_streaming_data(self, stream_response):
        final_response = ""
        for chunk in stream_response.iter_lines():
            without_data = chunk.decode('utf-8')[6:]
            final_response += without_data
        return final_response
    
    
    # Deployment sanity tests
    @pytest.mark.vllm_tgi
    def test_documents_post(self, check_vllm_tgi_model_status):
        if check_vllm_tgi_model_status:
            url = self.DOCUMENT_URL            
            upload_response = self.upload_file(url, self.FILEPATHS, self.FILENAME)
            assert upload_response.status_code == 200, upload_response.json()
        else: 
            assert False, "Model failed to start."

    @pytest.mark.vllm_tgi
    def test_documents_get(self, check_vllm_tgi_model_status):
        if check_vllm_tgi_model_status:
            url = self.DOCUMENT_URL
            get_document_response = self.make_request(url, "GET")
            actual_file_name = get_document_response.json()[0]["file_name"]
            assert self.FILENAME[0][:-3] in actual_file_name
        else: 
            pytest.fail("Model failed to start.")

    @pytest.mark.vllm_tgi
    def test_stream_log_post(self, check_vllm_tgi_model_status):
        if check_vllm_tgi_model_status:
            url = self.STEAM_LOG_URL
            payload = json.dumps(self.PAYLOAD)            
            stream_response = self.make_request(url, "POST", payload, stream=True)
            actual_answer = self.get_streaming_data(stream_response)
            assert self.EXP_ANSWER in actual_answer or stream_response.status_code == 200
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.vllm_tgi
    def test_documents_delete(self, check_vllm_tgi_model_status):
        if check_vllm_tgi_model_status:
            url = self.DOCUMENT_URL            
            get_document_response = self.make_request(url, "DELETE", params=self.DELETE_DOC_PARAMS)
            assert get_document_response.status_code == 204
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.vllm_tgi
    def test_data_post(self, check_vllm_tgi_model_status):
        if check_vllm_tgi_model_status:
            url = self.DATA_STORE_URL
            upload_response = self.upload_file(url, self.FILEPATHS, self.FILENAME, params=self.DATA_STORE_PARAMS, files='file')
            assert upload_response.status_code == 201
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.vllm_tgi
    def test_data_get(self, check_vllm_tgi_model_status):
        if check_vllm_tgi_model_status:
            file_present = False
            url = self.DATA_STORE_URL
            get_document_response = self.make_request(url, "GET")
            files = get_document_response.json()['files']
            for file in files:
                if self.DATA_STORE_PARAMS["dest_file_name"] in file:
                    file_present = True
                    break
            assert file_present
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.vllm_tgi
    def test_data_delete(self, check_vllm_tgi_model_status):
        if check_vllm_tgi_model_status:
            url = self.DATA_STORE_URL            
            get_document_response = self.make_request(url, "DELETE", params=self.DELETE_DOC_PARAMS)
            assert get_document_response.status_code == 204
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.ovms
    def test_ovms_documents_post(self, check_ovms_model_status):
        if check_ovms_model_status:
            url = self.DOCUMENT_URL            
            upload_response = self.upload_file(url, self.FILEPATHS, self.FILENAME)
            assert upload_response.status_code == 200, upload_response.json()
        else: 
            assert False, "Model failed to start."

    @pytest.mark.ovms
    def test_ovms_documents_get(self, check_ovms_model_status):
        if check_ovms_model_status:
            url = self.DOCUMENT_URL
            get_document_response = self.make_request(url, "GET")
            actual_file_name = get_document_response.json()[0]["file_name"]
            assert self.FILENAME[0][:-3] in actual_file_name
        else: 
            pytest.fail("Model failed to start.")

    @pytest.mark.ovms
    def test_ovms_stream_log_post(self, check_ovms_model_status):
        if check_ovms_model_status:
            url = self.STEAM_LOG_URL
            payload = json.dumps(self.PAYLOAD)            
            stream_response = self.make_request(url, "POST", payload, stream=True)
            actual_answer = self.get_streaming_data(stream_response)
            assert self.EXP_ANSWER in actual_answer or stream_response.status_code == 200
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.ovms
    def test_ovms_documents_delete(self, check_ovms_model_status):
        if check_ovms_model_status:
            url = self.DOCUMENT_URL            
            get_document_response = self.make_request(url, "DELETE", params=self.DELETE_DOC_PARAMS)
            assert get_document_response.status_code == 204
        else: 
            pytest.fail("Model failed to start.")
    
    def test_ovms_data_post(self, check_ovms_model_status):
        if check_ovms_model_status:
            url = self.DATA_STORE_URL
            upload_response = self.upload_file(url, self.FILEPATHS, self.FILENAME, params=self.DATA_STORE_PARAMS, files='file')
            assert upload_response.status_code == 201
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.ovms
    def test_ovms_data_get(self, check_ovms_model_status):
        if check_ovms_model_status:
            file_present = False
            url = self.DATA_STORE_URL
            get_document_response = self.make_request(url, "GET")
            files = get_document_response.json()['files']
            for file in files:
                if self.DATA_STORE_PARAMS["dest_file_name"] in file:
                    file_present = True
                    break
            assert file_present
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.ovms
    def test_ovms_data_delete(self, check_ovms_model_status):
        if check_ovms_model_status:
            url = self.DATA_STORE_URL            
            get_document_response = self.make_request(url, "DELETE", params=self.DELETE_DOC_PARAMS)
            assert get_document_response.status_code == 204
        else: 
            pytest.fail("Model failed to start.")
    

    @pytest.mark.core
    def test_core_documents_post(self, check_chatqna_core_status):
        if check_chatqna_core_status:
            url = self.DOCUMENT_URL            
            upload_response = self.upload_file(url, self.FILEPATHS, self.FILENAME)
            assert upload_response.status_code == 200, upload_response.json()
        else: 
            assert False, "Model failed to start."

    @pytest.mark.core
    def test_core_documents_get(self, check_chatqna_core_status):
        if check_chatqna_core_status:
            url = self.DOCUMENT_URL
            get_document_response = self.make_request(url, "GET")
            actual_file_name = get_document_response.json()[0]["file_name"]
            assert self.FILENAME[0][:-3] in actual_file_name
        else: 
            pytest.fail("Model failed to start.")

    @pytest.mark.core
    def test_core_stream_log_post(self, check_chatqna_core_status):
        if check_chatqna_core_status:
            url = self.STEAM_LOG_URL
            payload = json.dumps(self.PAYLOAD)            
            stream_response = self.make_request(url, "POST", payload, stream=True)
            actual_answer = self.get_streaming_data(stream_response)
            assert self.EXP_ANSWER in actual_answer or stream_response.status_code == 200
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.core
    def test_core_documents_delete(self, check_chatqna_core_status):
        if check_chatqna_core_status:
            url = self.DOCUMENT_URL            
            get_document_response = self.make_request(url, "DELETE", params=self.DELETE_DOC_PARAMS)
            assert get_document_response.status_code == 204
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.core
    def test_core_data_post(self, check_chatqna_core_status):
        if check_chatqna_core_status:
            url = self.DATA_STORE_URL
            upload_response = self.upload_file(url, self.FILEPATHS, self.FILENAME, params=self.DATA_STORE_PARAMS, files='file')
            assert upload_response.status_code == 201
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.core
    def test_core_data_get(self, check_chatqna_core_status):
        if check_chatqna_core_status:
            file_present = False
            url = self.DATA_STORE_URL
            get_document_response = self.make_request(url, "GET")
            files = get_document_response.json()['files']
            for file in files:
                if self.DATA_STORE_PARAMS["dest_file_name"] in file:
                    file_present = True
                    break
            assert file_present
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.core
    def test_core_data_delete(self, check_chatqna_core_status):
        if check_chatqna_core_status:
            url = self.DATA_STORE_URL            
            get_document_response = self.make_request(url, "DELETE", params=self.DELETE_DOC_PARAMS)
            assert get_document_response.status_code == 204
        else: 
            pytest.fail("Model failed to start.")



    @pytest.mark.helm
    def test_helm_documents_post(self, check_chatqna_helm_status):
        if check_chatqna_helm_status:
            url = self.DOCUMENT_URL            
            upload_response = self.upload_file(url, self.FILEPATHS, self.FILENAME)
            assert upload_response.status_code == 200, upload_response.json()
        else: 
            assert False, "Model failed to start."

    @pytest.mark.helm
    def test_helm_documents_get(self, check_chatqna_helm_status):
        if check_chatqna_helm_status:
            url = self.DOCUMENT_URL
            get_document_response = self.make_request(url, "GET")
            actual_file_name = get_document_response.json()[0]["file_name"]
            assert self.FILENAME[0][:-3] in actual_file_name
        else: 
            pytest.fail("Model failed to start.")

    @pytest.mark.helm
    def test_helm_stream_log_post(self, check_chatqna_helm_status):
        if check_chatqna_helm_status:
            url = self.HELM_CHAT
            payload = json.dumps(self.PAYLOAD)            
            stream_response = self.make_request(url, "POST", payload, stream=True)
            actual_answer = self.get_streaming_data(stream_response)
            assert self.EXP_ANSWER in actual_answer or stream_response.status_code == 200
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.helm
    def test_helm_documents_delete(self, check_chatqna_helm_status):
        if check_chatqna_helm_status:
            url = self.DOCUMENT_URL            
            get_document_response = self.make_request(url, "DELETE", params=self.DELETE_DOC_PARAMS)
            assert get_document_response.status_code == 204
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.helm
    def test_helm_data_post(self, check_chatqna_helm_status):
        if check_chatqna_helm_status:
            url = self.HELM_DATA_STORE_URL
            upload_response = self.upload_file(url, self.FILEPATHS, self.FILENAME, params=self.DATA_STORE_PARAMS, files='file')
            assert upload_response.status_code == 201
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.helm
    def test_helm_data_get(self, check_chatqna_helm_status):
        if check_chatqna_helm_status:
            file_present = False
            url = self.HELM_DATA_STORE_URL
            get_document_response = self.make_request(url, "GET")
            files = get_document_response.json()['files']
            for file in files:
                if self.DATA_STORE_PARAMS["dest_file_name"] in file:
                    file_present = True
                    break
            assert file_present
        else: 
            pytest.fail("Model failed to start.")
    
    @pytest.mark.helm
    def test_helm_data_delete(self, check_chatqna_helm_status):
        if check_chatqna_helm_status:
            url = self.HELM_DATA_STORE_URL            
            get_document_response = self.make_request(url, "DELETE", params=self.DELETE_DOC_PARAMS)
            assert get_document_response.status_code == 204
        else: 
            pytest.fail("Model failed to start.")
