# AdvisoryBoard API Documentation

## Overview

The AdvisoryBoard API is a FastAPI-based backend for AI-powered client context management for CPA firms.

**Base URL:** `http://localhost:8000`

---

## Endpoints

### GET /

Returns the API status.

**Response:**
```json
{
  "status": "AdvisoryBoard API is running"
}
```

---

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy"
}
```

---

## Running Locally

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Interactive docs available at: `http://localhost:8000/docs`
