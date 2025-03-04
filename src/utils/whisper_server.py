#!/usr/bin/env python3

from flask import Flask, request, jsonify
import numpy as np
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
import os
import sys
import warnings
import logging

# Configure logging to suppress specific warnings
logging.getLogger("transformers").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=FutureWarning)

app = Flask(__name__)
progress_file = '/tmp/MAGI/whisper_progress'
SAMPLE_RATE = 16000  # Whisper expects 16kHz audio

def update_progress(message, percentage):
    os.makedirs('/tmp/MAGI', exist_ok=True)
    with open(progress_file, 'w') as f:
        f.write(f"{percentage}|{message}")

# Initialize progress
update_progress("Starting Whisper initialization...", 0)

try:
    update_progress("Checking CUDA availability...", 10)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

    update_progress("Loading Whisper model files...", 20)
    model_id = "openai/whisper-large-v3-turbo"

    update_progress("Loading model weights...", 30)
    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        model_id, torch_dtype=torch_dtype, low_cpu_mem_usage=True, use_safetensors=True
    )
    update_progress("Moving model to device...", 50)
    model.to(device)

    update_progress("Loading processor...", 70)
    processor = AutoProcessor.from_pretrained(model_id)

    update_progress("Setting up pipeline...", 90)
    # Update pipeline to use new parameter names and settings
    pipe = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        torch_dtype=torch_dtype,
        device=device,
        model_kwargs={"language": "en"}  # Force English output
    )

    update_progress("Ready", 100)

except Exception as e:
    update_progress(f"Error: {str(e)}", -1)
    print(f"Fatal error: {e}", file=sys.stderr)
    sys.exit(1)

@app.route('/transcribe', methods=['POST'])
def transcribe():
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400
    
    try:
        audio_file = request.files['audio']
        audio_data = np.frombuffer(audio_file.read(), dtype=np.float32)
        
        # Handle both input formats
        if "input_features" in str(request.headers.get('Content-Type', '')):
            # Direct feature input
            inputs = {"input_features": audio_data}
        else:
            # Raw audio input
            inputs = {
                "raw": audio_data,
                "sampling_rate": SAMPLE_RATE
            }
        
        # Process the audio
        result = pipe(inputs)
        transcription = result['text'].strip()
        
        return jsonify({'transcription': transcription})
    except Exception as e:
        print(f"Transcription error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/status', methods=['GET'])
def status():
    try:
        with open(progress_file, 'r') as f:
            progress = f.read().strip()
            percentage, message = progress.split('|', 1)
            return jsonify({
                'percentage': int(percentage),
                'message': message
            })
    except Exception as e:
        return jsonify({
            'percentage': -1,
            'message': f'Error reading status: {str(e)}'
        })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
