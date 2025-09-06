# one-shot run
python -m app.run_local
python -m app.peek_db

# api
python -m uvicorn app.server:app --reload
# call it (keep same thread_id to see checkpointing)
$tid = [guid]::NewGuid().ToString()
Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8000/run" `
  -ContentType "application/json" `
  -Body (@{ query="instructional design evidence synthesis"; thread_id=$tid } | ConvertTo-Json) | ConvertTo-Json
