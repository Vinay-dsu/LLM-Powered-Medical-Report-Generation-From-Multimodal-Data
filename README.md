2 datasets are used from kaggle
chest xray datatset - https://www.kaggle.com/datasets/simhadrisadaram/mimic-cxr-dataset
clinical history dataset - https://www.kaggle.com/datasets/montassarba/mimic-iv-clinical-database-demo-2-2

2 pre-trained models are used,
1. RAD-dino a VIT model partcularly trained for radiology purpose
2. BIO-GPT for patient history training

Install the requirements GPU CUDA version for better handling of this project


# LLM-Powered Medical Report Generation From Multimodal Data

This project is a web-based artificial intelligence application designed to automatically generate clinical radiology reports from chest X-ray images. It uses a state-of-the-art multimodal architecture, fusing Vision Transformers (ViT) with a specialized Large Language Model (BioGPT), to generate highly accurate and structured medical reports based on visual findings and patient history.

## 🚀 Features

- **Automated Report Generation**: Upload a chest X-ray image and get a detailed AI-generated clinical report.
- **Multimodal Architecture**: Uses a Vision Transformer (ViT/rad-dino) for image embedding and BioGPT for autoregressive text generation.
- **Patient History Integration**: Takes optional patient history input to provide more contextually accurate radiology reports.
- **Structured Output**: Automatically parses the generated raw text into logical clinical sections (Findings, Impression, Recommendations).
- **Web Interface**: A modern, easy-to-use web UI built with HTML/CSS/JS communicating with a Flask backend.

## 🛠️ Technology Stack

- **Backend / Web Server**: Flask, Flask-CORS
- **Machine Learning / AI**: PyTorch, Transformers (Hugging Face)
- **Image Processing**: Pillow, torchvision
- **Language Models**: BioGPT (`microsoft/biogpt`)
- **Vision Models**: Rad-DINO (`microsoft/rad-dino`) or fallback to ViT (`google/vit-base-patch16-224-in21k`)

## 📦 Project Structure

```text
.
├── app.py                     # Main Flask application and model inference logic
├── requirements.txt           # Python package dependencies
├── static/                    # Frontend assets (index.html, CSS, JS)
├── version_5/                 # Directory containing the pre-trained model checkpoint (best_multimodal_v5.pt)
├── test_images/               # Sample X-ray images for testing
├── Project_Report.docx        # Project documentation and details
└── ...                        # Evaluation scripts, benchmark data, and Jupyter notebooks
```

## ⚙️ Installation & Setup

Follow these steps to set up the project on your local machine.

### 1. Prerequisites
Ensure you have Python 3.8 or higher installed on your system.
You can download Python from [python.org](https://www.python.org/downloads/).

### 2. Clone the Repository
Clone this repository to your local machine and navigate to the project directory:
```bash
git clone <your-repository-url>
cd "LLM powered medical report generator"
```

### 3. Create a Virtual Environment
It is highly recommended to use a virtual environment to manage project dependencies.

**On Windows:**
```cmd
python -m venv venv
venv\Scripts\activate
```

**On macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies
Once the virtual environment is activated, install the required packages using `pip`:
```bash
pip install -r requirements.txt
```

*(Note: Depending on your system and whether you have a CUDA-compatible GPU, you might need to install a specific version of PyTorch from the [official website](https://pytorch.org/get-started/locally/) before running the above command).*

### 5. Model Checkpoint Setup
Ensure that the latest model checkpoint (`best_multimodal_v5.pt`) is located in the `version_5` directory:
```text
version_5/best_multimodal_v5.pt
```

## 🖥️ Running the Application

1. Make sure your virtual environment is activated.
2. Run the Flask server:
```bash
python app.py
```
3. Wait for the model to load into memory (this may take a minute depending on your hardware. If a compatible GPU is detected, it will automatically use `cuda`, otherwise it will fall back to `cpu`).
4. Once the server is running, open your web browser and navigate to:
```text
http://localhost:5000
```
5. You can now use the interface to upload X-ray images, provide patient history, and generate reports.

## ⚠️ Disclaimer
**This application is built for academic and research purposes only.** The AI-generated reports are NOT a substitute for professional medical diagnosis. Always consult a qualified radiologist or physician for clinical decisions.
