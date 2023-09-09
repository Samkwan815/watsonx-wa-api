# main.py
import concurrent.futures
from fastapi import FastAPI, BackgroundTasks
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from pymongo import MongoClient

app = FastAPI()

class GenerateRequest(BaseModel):
    model_id: str
    input: str
    project_id: str
    decoding_method: str
    max_new_tokens: int
    repetition_penalty: float
    apikey: str

class GenerationStatus(BaseModel):
    job_id: str
    status: str
    result: str = None

job_statuses = {}

# Connect to MongoDB
#client = MongoClient("mongodb://localhost:27017/")
#db = client["generated_texts"]
#collection = db["results"]

def perform_generation(payload: GenerateRequest, job_id: str):
    model_id = payload.model_id
    input_data = payload.input
    project_id = payload.project_id
    decoding_method = payload.decoding_method
    max_new_tokens = payload.max_new_tokens
    repetition_penalty = payload.repetition_penalty
    apikey = payload.apikey

    # Create Class for prompt request
    import requests

    class Prompt:
        def __init__(self, access_token, project_id):
            self.access_token = access_token
            self.project_id = project_id

        def generate(self, input, model_id, parameters):
            wml_url = "https://us-south.ml.cloud.ibm.com/ml/v1-beta/generation/text?version=2023-05-28"
            Headers = {
                "Authorization": "Bearer " + self.access_token,
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            data = {
                "model_id": model_id,
                "input": input,
                "parameters": parameters,
                "project_id": self.project_id
            }
            response = requests.post(wml_url, json=data, headers=Headers)
            if response.status_code == 200:
                return response.json()["results"][0]["generated_text"]
            else:
                return response.text
            
    from ibm_cloud_sdk_core import IAMTokenManager
    #from ibm_cloud_sdk_core.authenticators import IAMAuthenticator, BearerTokenAuthenticator
    import getpass

    access_token = IAMTokenManager(
        apikey = apikey,
        url = "https://iam.cloud.ibm.com/identity/token"
    ).get_token()

    parameters = {
        "decoding_method": decoding_method,
        "max_new_tokens": max_new_tokens,
        "repetition_penalty": repetition_penalty
    }

    prompt_input = input_data

    prompt = Prompt(access_token, project_id)

    answer = prompt.generate(prompt_input, model_id, parameters)

    job_statuses[job_id]["status"] = "completed"
    job_statuses[job_id]["result"] = answer

    # Save the completed result to MongoDB
    #collection.insert_one({"job_id": job_id, "result": answer})

@app.post("/genai/")
async def generate(payload: GenerateRequest, background_tasks: BackgroundTasks):
    import uuid
    job_id = str(uuid.uuid4())

    # Create a new job status entry
    job_statuses[job_id] = {"status": "running", "result": None}

    # Perform generation in the background
    background_tasks.add_task(perform_generation, payload, job_id)

    # Return the job ID
    return {"Request received - job_id": job_id, "status": "running"}

@app.get("/genai/{job_id}/status")
async def get_generation_status(job_id: str):
    if job_id not in job_statuses:
        return {"message": "Job ID not found"}

    status_info = job_statuses[job_id]
    return status_info

@app.get("/genai/{job_id}/result")
async def get_generation_result(job_id: str):
    if job_id not in job_statuses:
        return {"message": "Job ID not found"}

    status_info = job_statuses[job_id]
    if status_info["status"] != "completed":
        return {"message": "Job is not yet completed"}

    result = status_info["result"]

    # Delete job and its result from the dictionary
    del job_statuses[job_id]

    return {"result": result}

@app.get("/openapi.json")
async def get_open_api_endpoint():
    return get_openapi(
        title="watsonx.ai converter",
        version="1.0",
        description="API documentation for watsonx.ai converter FastAPI application.",
        routes=app.routes,
    )
