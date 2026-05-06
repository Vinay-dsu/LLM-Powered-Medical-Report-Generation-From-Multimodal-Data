# Deploying MedReport AI to Hugging Face Spaces (Free)

To deploy your backend AI model to the cloud so your frontend can connect to it from anywhere, **Hugging Face Spaces** is the best free option for hosting Python ML apps.

Here is the step-by-step guide to get it running for free.

---

## Part 1: Setting up the Hugging Face Space

1. **Create an Account:**
   Go to [huggingface.co](https://huggingface.co/) and create a free account.
2. **Create a New Space:**
   Click your profile picture in the top right -> **New Space**.
   - **Space Name:** `medreport-ai-backend`
   - **License:** `MIT` (or your choice)
   - **Select the Space SDK:** Choose **Docker** (Blank). *Do not select Gradio or Streamlit since we are using our own custom Flask API.*
   - **Space Hardware:** Select **Free (CPU basic - 16GB RAM, 2 vCPU)**. Note that on the free tier, inference will take ~30-60 seconds on the CPU.
3. **Click "Create Space"**

---

## Part 2: Uploading the Files to the Space

Now that the space is created, you need to upload three files to the root directory of your Space repository.

### 1. `app.py`
Upload the `app.py` file from your local computer. *Note: Ensure your `CHECKPOINT_PATH` in `app.py` points to the correct Hugging Face Hub model if you don't upload the massive 1.78GB `.pt` file directly to the space.*

### 2. `requirements.txt`
In the Space UI, click **Add file** -> **Create new file**. Name it `requirements.txt` and paste this exactly:
```text
flask==3.0.0
flask-cors==4.0.0
torch==2.1.0
torchvision==0.16.0
transformers==4.35.0
pillow==10.1.0
numpy==1.26.2
```

### 3. `Dockerfile`
Create a new file named `Dockerfile`. This tells Hugging Face how to run your Flask application on port 7860 (the default port for HF Spaces). Paste this:
```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (needed for OpenCV/PIL if required)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Expose the HF default port
EXPOSE 7860

# Run the flask server
CMD ["flask", "run", "--host=0.0.0.0", "--port=7860"]
```

Once committed, the Space will change from "Building" to "Running". This process installs all prerequisites.

---

## Part 3: Connecting Your Local Frontend

When the Space is running, click the three dots (`...`) in the top right corner of the Space and select **Embed this Space**. It will show you the direct URL (something like `https://yourusername-medreport-ai-backend.hf.space`).

1. **Open your local `script.js`** file.
2. Find the `/api/generate` fetch call (around line 116):
   ```javascript
   const res = await fetch('/api/generate', {
   ```
3. Change it to point to your new live Hugging Face URL:
   ```javascript
   const res = await fetch('https://YOUR_USERNAME-medreport-ai-backend.hf.space/api/generate', {
   ```
4. **Important:** Because your frontend (running locally or on Vercel/Netlify) is calling a different domain (Hugging Face), the Flask backend *must* allow Cross-Origin Resource Sharing (CORS).

### Enabling CORS in `app.py` (Already updated locally)
I just updated your local `app.py` to include `CORS`. When you upload `app.py` to HuggingFace, make sure it has these lines at the top:
```python
from flask_cors import CORS

app = Flask(__name__, static_folder='static')
CORS(app) # <--- This line allows ANY frontend to connect to the backend API!
```

---
**Done!** Your backend is now hosted in the cloud, and your local HTML website can send X-ray images directly to it for inference!
