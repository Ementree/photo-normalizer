"""Web UI for Photo Normalizer."""

import os
import threading
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from flask import Flask, render_template, request, jsonify, send_from_directory
import uuid
import platform
import subprocess

from .cli import iter_input_files, determine_capture_datetime, get_file_times


app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')

# Store processing jobs
processing_jobs: Dict[str, Dict[str, Any]] = {}

# Default folders (override via env)
DEFAULT_INPUT_DIR = Path(
    os.getenv("DEFAULT_INPUT_DIR", (Path.cwd() / "input").as_posix())
).resolve()
DEFAULT_OUTPUT_DIR = Path(
    os.getenv("DEFAULT_OUTPUT_DIR", (Path.cwd() / "output").as_posix())
).resolve()

# Detect docker runtime
RUNNING_IN_DOCKER = bool(os.getenv("RUNNING_IN_DOCKER")) or Path("/.dockerenv").exists()

# Ensure default folders exist
DEFAULT_INPUT_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@app.route('/')
def index():
    """Main page with folder selection UI."""
    return render_template(
        'index.html',
        default_input=str(DEFAULT_INPUT_DIR),
        default_output=str(DEFAULT_OUTPUT_DIR),
        running_in_docker=RUNNING_IN_DOCKER,
    )


@app.route('/api/validate-folder', methods=['POST'])
def validate_folder():
    """Validate if a folder path exists and contains photos."""
    data = request.get_json()
    folder_path = data.get('path', '')
    
    if not folder_path:
        return jsonify({'valid': False, 'error': 'No path provided'})
    
    path = Path(folder_path)
    if not path.exists():
        return jsonify({'valid': False, 'error': 'Path does not exist'})
    
    if not path.is_dir():
        return jsonify({'valid': False, 'error': 'Path is not a directory'})
    
    # Check if folder contains supported image files
    try:
        image_files = list(iter_input_files(path, recursive=True))
        return jsonify({
            'valid': True, 
            'image_count': len(image_files),
            'message': f'Found {len(image_files)} supported image files'
        })
    except Exception as e:
        return jsonify({'valid': False, 'error': f'Error scanning folder: {str(e)}'})


@app.route('/api/pick-folder', methods=['POST'])
def pick_folder():
    """Open a native folder picker (macOS only) and return the selected path."""
    system = platform.system()
    prompt = request.get_json(silent=True) or {}
    title = prompt.get('title', 'Select a folder')

    if system == 'Darwin':
        try:
            # Use AppleScript to open a folder chooser and return POSIX path
            # Escape any quotes in title to keep AppleScript valid
            title_safe = title.replace('"', '\\"')
            script = f'POSIX path of (choose folder with prompt "{title_safe}")'
            result = subprocess.run(
                ["osascript", "-e", script],
                check=True,
                capture_output=True,
                text=True,
            )
            path = result.stdout.strip()
            if not path:
                return jsonify({'cancelled': True}), 200
            return jsonify({'path': path}), 200
        except subprocess.CalledProcessError as e:
            # User may have cancelled
            return jsonify({'cancelled': True}), 200
        except Exception as e:
            return jsonify({'error': f'Folder picker failed: {e}'}), 500
    else:
        return jsonify({'error': f'Folder picker not supported on {system}. Please paste the path manually.'}), 400


@app.route('/api/process', methods=['POST'])
def process_photos():
    """Start photo processing job."""
    data = request.get_json()
    
    input_dir = data.get('input_dir')
    output_dir = data.get('output_dir')
    options = data.get('options', {})
    
    if not input_dir or not output_dir:
        return jsonify({'error': 'Input and output directories are required'}), 400
    
    # Create unique job ID
    job_id = str(uuid.uuid4())
    
    # Initialize job status
    processing_jobs[job_id] = {
        'status': 'starting',
        'progress': 0,
        'total': 0,
        'current_file': '',
        'start_time': datetime.now(),
        'completed_files': 0,
        'error': None
    }
    
    # Start processing in background thread
    thread = threading.Thread(
        target=process_photos_worker,
        args=(job_id, input_dir, output_dir, options)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({'job_id': job_id})


def process_photos_worker(job_id: str, input_dir: str, output_dir: str, options: Dict[str, Any]):
    """Background worker for photo processing."""
    try:
        # Update job status
        processing_jobs[job_id]['status'] = 'scanning'
        
        # Get input files
        input_path = Path(input_dir)
        recursive = options.get('recursive', True)
        input_files = list(iter_input_files(input_path, recursive))
        
        processing_jobs[job_id]['total'] = len(input_files)
        
        if not input_files:
            processing_jobs[job_id]['status'] = 'error'
            processing_jobs[job_id]['error'] = 'No supported images found'
            return
        
        # Update status to processing
        processing_jobs[job_id]['status'] = 'processing'
        
        # Import and call the CLI main function with our parameters
        import sys
        from unittest.mock import patch
        
        # Prepare arguments for CLI
        args = [
            'photo-normalizer',
            input_dir,
            '-o', output_dir,
            '--format', options.get('format', 'jpeg'),
            '--quality', str(options.get('quality', 90)),
            '--subfolders', options.get('subfolders', 'none')
        ]
        
        if options.get('recursive', True):
            args.append('-r')
        
        if not options.get('keep_metadata', True):
            args.append('--strip-metadata')
        
        if options.get('copy_unchanged', True):
            args.append('--copy-unchanged')
        
        # Mock sys.argv and call the CLI function
        with patch.object(sys, 'argv', args):
            # We'll implement a custom version that updates progress
            process_with_progress(job_id, input_path, Path(output_dir), options)
            
        processing_jobs[job_id]['status'] = 'completed'
        processing_jobs[job_id]['progress'] = 100
        
    except Exception as e:
        processing_jobs[job_id]['status'] = 'error'
        processing_jobs[job_id]['error'] = str(e)


def process_with_progress(job_id: str, input_dir: Path, output_dir: Path, options: Dict[str, Any]):
    """Process photos with progress updates."""
    from .cli import (
        PlanItem, OUTPUT_FORMAT_TO_EXT, build_target_path, 
        ensure_unique, save_image
    )
    
    # Get processing parameters
    output_format = options.get('format', 'jpeg')
    quality = options.get('quality', 90)
    keep_metadata = options.get('keep_metadata', True)
    subfolders = options.get('subfolders', 'none')
    copy_unchanged = options.get('copy_unchanged', True)
    recursive = options.get('recursive', True)
    
    target_ext = OUTPUT_FORMAT_TO_EXT[output_format]
    input_files = list(iter_input_files(input_dir, recursive))
    
    # Build processing plan
    plan = []
    for i, path in enumerate(input_files):
        processing_jobs[job_id]['current_file'] = path.name
        processing_jobs[job_id]['progress'] = int((i / len(input_files)) * 20)  # 20% for planning
        
        try:
            capture_dt = determine_capture_datetime(path)
        except Exception:
            capture_dt = get_file_times(path)

        needs_reencode = True
        if copy_unchanged and path.suffix.lower() == target_ext:
            needs_reencode = False

        plan.append(
            PlanItem(
                source=path,
                capture_dt=capture_dt,
                target=Path(),  # placeholder
                needs_reencode=needs_reencode,
            )
        )

    # Sort by capture date
    plan.sort(key=lambda p: (p.capture_dt, p.source.name))

    # Assign target paths
    last_second = None
    seq_in_second = 0
    for item in plan:
        current_second = item.capture_dt.replace(microsecond=0)
        if last_second is None or current_second != last_second:
            seq_in_second = 1
            last_second = current_second
        else:
            seq_in_second += 1
        target_path = build_target_path(output_dir, item.capture_dt, seq_in_second, subfolders, target_ext)
        item.target = ensure_unique(target_path)

    # Process files
    processing_jobs[job_id]['status'] = 'processing'
    for i, item in enumerate(plan):
        processing_jobs[job_id]['current_file'] = item.source.name
        processing_jobs[job_id]['progress'] = int(20 + (i / len(plan)) * 80)  # 20-100%
        processing_jobs[job_id]['completed_files'] = i
        
        save_image(
            src_path=item.source,
            dest_path=item.target,
            output_format=output_format,
            quality=quality,
            keep_metadata=keep_metadata,
            reencode=item.needs_reencode,
        )


@app.route('/api/status/<job_id>')
def get_job_status(job_id):
    """Get processing job status."""
    if job_id not in processing_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = processing_jobs[job_id].copy()
    
    # Add elapsed time
    if 'start_time' in job:
        elapsed = datetime.now() - job['start_time']
        job['elapsed_seconds'] = int(elapsed.total_seconds())
    
    return jsonify(job)


@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files."""
    return send_from_directory(app.static_folder, filename)


def run_web_app(host='127.0.0.1', port=5000, debug=False):
    """Run the web application."""
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    run_web_app(debug=True)
