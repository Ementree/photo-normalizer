// Photo Normalizer Web UI JavaScript

class PhotoNormalizerApp {
    constructor() {
        this.currentJobId = null;
        this.progressInterval = null;
        this.init();
    }

    init() {
        this.bindEvents();
        this.updateQualityDisplay();
        // Trigger initial validation so defaults are validated on load
        this.runInitialValidation();
    }

    bindEvents() {
        // Folder selection
        document.getElementById('browse-input').addEventListener('click', () => {
            this.nativePickFolder('input');
        });
        
        document.getElementById('browse-output').addEventListener('click', () => {
            this.nativePickFolder('output');
        });

        // Input validation
        document.getElementById('input-folder').addEventListener('input', () => {
            this.validateInputFolder();
        });

        document.getElementById('output-folder').addEventListener('input', () => {
            this.validateOutputFolder();
        });

        // Quality slider
        document.getElementById('quality').addEventListener('input', (e) => {
            this.updateQualityDisplay();
        });

        // Process button
        document.getElementById('start-processing').addEventListener('click', () => {
            this.startProcessing();
        });

        // Modal events
        document.getElementById('close-error-modal').addEventListener('click', () => {
            this.hideModal('error-modal');
        });

        document.getElementById('dismiss-error').addEventListener('click', () => {
            this.hideModal('error-modal');
        });

        // Results actions
        document.getElementById('open-output-folder').addEventListener('click', () => {
            this.openOutputFolder();
        });

        document.getElementById('process-more').addEventListener('click', () => {
            this.resetForNewProcess();
        });

        // Form validation on change
        ['input-folder', 'output-folder'].forEach(id => {
            document.getElementById(id).addEventListener('input', () => {
                this.validateForm();
            });
        });
    }

    runInitialValidation() {
        // Validate defaults on first load
        // Fire and forget; each method updates UI accordingly
        this.validateInputFolder();
        this.validateOutputFolder();
        this.validateForm();
    }

    async nativePickFolder(type) {
        try {
            const resp = await fetch('/api/pick-folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: type === 'input' ? 'Select input folder' : 'Select output folder' })
            });
            const res = await resp.json();
            if (res.cancelled) return;
            if (res.error) throw new Error(res.error);
            const folderPath = res.path;
            if (type === 'input') {
                document.getElementById('input-folder').value = folderPath;
                this.validateInputFolder();
            } else {
                document.getElementById('output-folder').value = folderPath;
                this.validateOutputFolder();
            }
            this.validateForm();
        } catch (error) {
            console.error('Error browsing folder:', error);
            this.showError(error.message || 'Folder browsing is not supported. Please type the path manually.');
        }
    }

    async validateInputFolder() {
        const folderPath = document.getElementById('input-folder').value.trim();
        const statusEl = document.getElementById('input-status');
        
        if (!folderPath) {
            statusEl.className = 'folder-status';
            statusEl.style.display = 'none';
            return false;
        }

        try {
            const response = await fetch('/api/validate-folder', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ path: folderPath })
            });

            const result = await response.json();
            
            if (result.valid) {
                statusEl.className = 'folder-status success';
                statusEl.textContent = `✓ ${result.message}`;
                statusEl.style.display = 'block';
                return true;
            } else {
                statusEl.className = 'folder-status error';
                statusEl.textContent = `✗ ${result.error}`;
                statusEl.style.display = 'block';
                return false;
            }
        } catch (error) {
            console.error('Error validating folder:', error);
            statusEl.className = 'folder-status error';
            statusEl.textContent = '✗ Error validating folder';
            statusEl.style.display = 'block';
            return false;
        }
    }

    validateOutputFolder() {
        const folderPath = document.getElementById('output-folder').value.trim();
        const statusEl = document.getElementById('output-status');
        
        if (!folderPath) {
            statusEl.className = 'folder-status';
            statusEl.style.display = 'none';
            return false;
        }

        // Basic validation - in a real app you'd check if the path is writable
        if (folderPath.length > 0) {
            statusEl.className = 'folder-status success';
            statusEl.textContent = '✓ Output folder set';
            statusEl.style.display = 'block';
            return true;
        } else {
            statusEl.className = 'folder-status error';
            statusEl.textContent = '✗ Invalid output folder';
            statusEl.style.display = 'block';
            return false;
        }
    }

    validateForm() {
        const inputFolder = document.getElementById('input-folder').value.trim();
        const outputFolder = document.getElementById('output-folder').value.trim();
        const processBtn = document.getElementById('start-processing');
        
        const isValid = inputFolder && outputFolder;
        processBtn.disabled = !isValid;
        
        return isValid;
    }

    updateQualityDisplay() {
        const qualitySlider = document.getElementById('quality');
        const qualityValue = document.querySelector('.quality-value');
        qualityValue.textContent = qualitySlider.value;
    }

    async startProcessing() {
        if (!this.validateForm()) {
            this.showError('Please select both input and output folders.');
            return;
        }

        const options = this.getProcessingOptions();
        const inputDir = document.getElementById('input-folder').value.trim();
        const outputDir = document.getElementById('output-folder').value.trim();

        try {
            // Hide other sections and show progress
            document.getElementById('folder-selection').style.display = 'none';
            document.getElementById('options-card').style.display = 'none';
            document.querySelector('.action-section').style.display = 'none';
            document.getElementById('progress-card').style.display = 'block';

            const response = await fetch('/api/process', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    input_dir: inputDir,
                    output_dir: outputDir,
                    options: options
                })
            });

            const result = await response.json();
            
            if (response.ok) {
                this.currentJobId = result.job_id;
                this.startProgressPolling();
            } else {
                throw new Error(result.error || 'Failed to start processing');
            }
        } catch (error) {
            console.error('Error starting processing:', error);
            this.showError(`Failed to start processing: ${error.message}`);
            this.resetForNewProcess();
        }
    }

    getProcessingOptions() {
        return {
            format: document.getElementById('output-format').value,
            quality: parseInt(document.getElementById('quality').value),
            subfolders: document.getElementById('subfolders').value,
            recursive: document.getElementById('recursive').checked,
            keep_metadata: document.getElementById('keep-metadata').checked,
            copy_unchanged: document.getElementById('copy-unchanged').checked
        };
    }

    startProgressPolling() {
        this.progressInterval = setInterval(() => {
            this.updateProgress();
        }, 1000);
    }

    stopProgressPolling() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
            this.progressInterval = null;
        }
    }

    async updateProgress() {
        if (!this.currentJobId) return;

        try {
            const response = await fetch(`/api/status/${this.currentJobId}`);
            const status = await response.json();

            if (!response.ok) {
                throw new Error(status.error || 'Failed to get status');
            }

            this.updateProgressUI(status);

            if (status.status === 'completed') {
                this.stopProgressPolling();
                this.showResults(status);
            } else if (status.status === 'error') {
                this.stopProgressPolling();
                this.showError(`Processing failed: ${status.error}`);
                this.resetForNewProcess();
            }
        } catch (error) {
            console.error('Error updating progress:', error);
            this.stopProgressPolling();
            this.showError(`Error getting progress: ${error.message}`);
            this.resetForNewProcess();
        }
    }

    updateProgressUI(status) {
        // Update progress bar
        const progressFill = document.getElementById('progress-fill');
        const progressPercentage = document.getElementById('progress-percentage');
        progressFill.style.width = `${status.progress}%`;
        progressPercentage.textContent = `${status.progress}%`;

        // Update status text
        const progressText = document.getElementById('progress-text');
        const statusTexts = {
            'starting': 'Initializing...',
            'scanning': 'Scanning for photos...',
            'processing': 'Processing photos...',
            'completed': 'Processing complete!',
            'error': 'Error occurred'
        };
        progressText.textContent = statusTexts[status.status] || status.status;

        // Update details
        document.getElementById('current-file').textContent = status.current_file || '-';
        document.getElementById('completed-count').textContent = status.completed_files || 0;
        document.getElementById('total-count').textContent = status.total || 0;
        document.getElementById('elapsed-time').textContent = `${status.elapsed_seconds || 0}s`;
    }

    showResults(status) {
        document.getElementById('progress-card').style.display = 'none';
        document.getElementById('results-card').style.display = 'block';
        
        const message = `Successfully processed ${status.completed_files} photos in ${status.elapsed_seconds}s`;
        document.getElementById('results-message').textContent = message;
    }

    resetForNewProcess() {
        // Stop any ongoing polling
        this.stopProgressPolling();
        this.currentJobId = null;

        // Reset UI
        document.getElementById('progress-card').style.display = 'none';
        document.getElementById('results-card').style.display = 'none';
        document.getElementById('folder-selection').style.display = 'block';
        document.getElementById('options-card').style.display = 'block';
        document.querySelector('.action-section').style.display = 'block';

        // Reset progress
        document.getElementById('progress-fill').style.width = '0%';
        document.getElementById('progress-percentage').textContent = '0%';
        document.getElementById('progress-text').textContent = 'Ready';
        document.getElementById('current-file').textContent = '-';
        document.getElementById('completed-count').textContent = '0';
        document.getElementById('total-count').textContent = '0';
        document.getElementById('elapsed-time').textContent = '0s';

        // Re-validate form
        this.validateForm();
    }

    openOutputFolder() {
        const outputPath = document.getElementById('output-folder').value.trim();
        if (outputPath) {
            // In a real app, you'd open the folder in the system file manager
            // This would require either:
            // 1. Electron's shell.openPath()
            // 2. A server endpoint that opens the folder
            // 3. A browser download of a shortcut file
            alert(`Output folder: ${outputPath}\n\nIn a desktop app, this would open the folder in your file manager.`);
        }
    }

    showError(message) {
        document.getElementById('error-message').textContent = message;
        this.showModal('error-modal');
    }

    showModal(modalId) {
        document.getElementById(modalId).style.display = 'block';
    }

    hideModal(modalId) {
        document.getElementById(modalId).style.display = 'none';
    }
}

// Initialize the app when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new PhotoNormalizerApp();
});

// Example folder paths for demo purposes
document.addEventListener('DOMContentLoaded', () => {
    // Add some example paths for easy testing
    const inputFolder = document.getElementById('input-folder');
    const outputFolder = document.getElementById('output-folder');
    
    // Set placeholder example paths
    inputFolder.placeholder = 'e.g., /Users/yourname/Photos/iPhone or C:\\Users\\yourname\\Pictures\\Camera Roll';
    outputFolder.placeholder = 'e.g., /Users/yourname/Photos/Organized or C:\\Users\\yourname\\Pictures\\Organized';
    
    // Allow manual typing by making input not readonly after a click
    inputFolder.addEventListener('click', () => {
        inputFolder.removeAttribute('readonly');
        inputFolder.placeholder = 'Type or paste the folder path here...';
    });
});
