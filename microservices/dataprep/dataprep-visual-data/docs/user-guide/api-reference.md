# Dataprep Microservice API Reference

## Health Check
Endpoint: 

```
GET /v1/dataprep/health
```

Description: 

Checks the health status of the microservice.


Response:

-    200 OK: 
```
{
    "status": "healthy" 
}
```

-    500 Internal Server Error: 
```
{ 
    "detail": "Health check failed: <error_message>" 
}
```

## Info
Endpoint: 

```
GET /v1/dataprep/info
```

Description: 

Retrieves the current status of the microservice, including model information and the number of processed files.


Response:

-    200 OK:
```
{
    "model_id": "<model_id>",
    "model_path": "<model_path>",
    "device": "<device>",
    "Number of processed files": <count>
}
```

-    500 Internal Server Error: 
```
{ 
    "detail": "Error retrieving status info: <error_message>" 
}
```

## Ingest Files
Endpoint: 
```
POST /v1/dataprep/ingest
```

Description: 

Ingests files from a directory or a single file for preprocessing and embedding generation.


Request Body:

-    For Directory:
```
{
  "file_dir": "<directory_path>",
  "frame_extract_interval": 15,
  "do_detect_and_crop": true
}
```

-    For Single File:
```
{
  "file_path": "<file_path>",
  "meta": {
    "<key>": "<value>"
  },
  "frame_extract_interval": 15,
  "do_detect_and_crop": true
}
```

Response:

-    200 OK: 
```
{ 
    "message": "Files successfully processed. db returns <response>" 
}
```

-    400 Bad Request: 
```
{ 
    "detail": "Invalid file path." 
}
```

-    500 Internal Server Error: 
```
{ 
    "detail": "Error processing files: <error_message>" 
}
```

## Get File Info
Endpoint: 
```
GET /v1/dataprep/get
```

Description: 

Retrieves information about a file from the database.


Query Parameters:

-    file_path: Path to the file.


Response:
-    200 OK:
```
{
    "file_path": "<file_path>",
    "ids_in_db": ["<id1>", "<id2>"]
}
```

-    404 Not Found: 
```
{ 
    "detail": "File not found." 
}
```

-    500 Internal Server Error: 
```
{ 
    "detail": "Error retrieving file: <error_message>" 
}
```

## Delete File in Database
Endpoint: 
```
DELETE /v1/dataprep/delete
```

Description: 

Deletes a file entity from the database. Note: The original file is not deleted.


Query Parameters:

-    file_path: Path to the file.

Response:
-    200 OK:
```
{
    "message": "File successfully deleted. db returns: <response>",
    "removed_ids": ["<id1>", "<id2>"]
}
```

-    404 Not Found: 
```
{ 
    "detail": "File not found." 
}
```

-    500 Internal Server Error: 
```
{ 
    "detail": "Error deleting file: <error_message>" 
}
```

## Clear Database
Endpoint: 
```
DELETE /v1/dataprep/delete_all
```

Description: 

Clears all entries in the database. Note: The original files are not deleted.


Response:

-    200 OK: 
```
{ 
    "message": "Database successfully cleared. db returns: <response>" 
}
```

-    500 Internal Server Error: 
```
{ 
    "detail": "Error clearing database: <error_message>" 
}
```