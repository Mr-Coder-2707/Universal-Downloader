let isDownloading = false;
let statusInterval = null;

function playMusic() {
    const audio = document.getElementById('download-music');
    if (audio) {
        audio.currentTime = 0;
        audio.play().catch(e => console.log("Audio play failed:", e));
    }
}

function stopMusic() {
    const audio = document.getElementById('download-music');
    if (audio) {
        audio.pause();
        audio.currentTime = 0;
    }
}

function openTab(tabName) {
    const tabs = document.querySelectorAll('.tab-content');
    const buttons = document.querySelectorAll('.tab-btn');
    
    tabs.forEach(tab => tab.classList.remove('active'));
    buttons.forEach(btn => btn.classList.remove('active'));
    
    document.getElementById(tabName).classList.add('active');
    // Find the button that calls this function with this tabName
    const activeButton = Array.from(buttons).find(btn => btn.getAttribute('onclick').includes(tabName));
    if (activeButton) {
        activeButton.classList.add('active');
    }
}

async function fetchTitle(platform) {
    const url = document.getElementById(`${platform}-url`).value;
    if (!url) {
        alert('Please enter a URL');
        return;
    }

    const formData = new FormData();
    formData.append('url', url);

    try {
        document.getElementById('status-message').innerText = "Fetching video info...";
        const response = await fetch('/fetch_title', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (data.success) {
            document.getElementById(`${platform}-info`).style.display = 'flex';
            document.getElementById(`${platform}-title`).innerText = data.title;
            if (data.thumbnail) {
                document.getElementById(`${platform}-thumbnail`).src = data.thumbnail;
            }
            document.getElementById('status-message').innerText = "Video found!";
        } else {
            alert('Error: ' + data.title);
            document.getElementById('status-message').innerText = "Error fetching info";
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to fetch title');
    }
}

async function startDownload(platform) {
    if (isDownloading) {
        alert('A download is already in progress');
        return;
    }

    playMusic();

    const formData = new FormData();
    
    if (platform === 'instagram') {
        const url = document.getElementById('instagram-url').value;
        const folder = document.getElementById('instagram-folder').value;

        if (!url) {
            alert('Please enter an Instagram URL');
            return;
        }

        formData.append('url', url);
        formData.append('download_folder', folder);

        try {
            document.getElementById('status-message').innerText = "Downloading from Instagram...";
            const response = await fetch('/download_instagram', {
                method: 'POST',
                body: formData
            });
            const data = await response.json();
            
            if (data.success) {
                stopMusic();
                document.getElementById('status-message').innerText = data.message;
                alert(data.message);
                
                // Trigger browser download for Instagram files
                if (data.files && data.files.length > 0) {
                    data.files.forEach(file => {
                        const link = document.createElement('a');
                        link.href = `/downloads/${encodeURIComponent(file)}`;
                        link.download = file;
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                    });
                }
            } else {
                stopMusic();
                alert('Error: ' + data.message);
                document.getElementById('status-message').innerText = "Error: " + data.message;
            }
        } catch (error) {
            stopMusic();
            console.error('Error:', error);
            alert('Failed to download from Instagram');
        }
    } else {
        // YouTube, Facebook, TikTok
        const url = document.getElementById(`${platform}-url`).value;
        const quality = document.getElementById(`${platform}-quality`).value;
        const mode = document.getElementById(`${platform}-mode`).value;
        const folder = document.getElementById(`${platform}-folder`).value;
        
        if (!url) {
            alert('Please enter a URL');
            return;
        }

        formData.append('url', url);
        formData.append('quality', quality);
        formData.append('mode', mode);
        formData.append('download_folder', folder);
        formData.append('platform', platform);
        
        try {
            const response = await fetch('/start_download', {
                method: 'POST',
                body: formData
            });
            const data = await response.json();
            
            if (data.success) {
                startStatusPolling();
            } else {
                stopMusic();
                alert('Error: ' + data.message);
            }
        } catch (error) {
            stopMusic();
            console.error('Error:', error);
            alert('Failed to start download');
        }
    }
}

function startStatusPolling() {
    isDownloading = true;
    if (statusInterval) clearInterval(statusInterval);
    
    statusInterval = setInterval(async () => {
        try {
            const response = await fetch('/get_status');
            const data = await response.json();
            
            updateStatusUI(data);
            
            if (!data.is_downloading) {
                stopMusic();
                
                if (data.progress === 100) {
                    isDownloading = false;
                    clearInterval(statusInterval);
                    setTimeout(() => {
                         document.getElementById('status-message').innerText = "Download Finished!";
                         
                         // Trigger browser download
                         if (data.current_file) {
                             const link = document.createElement('a');
                             link.href = `/downloads/${encodeURIComponent(data.current_file)}`;
                             link.download = data.current_file;
                             document.body.appendChild(link);
                             link.click();
                             document.body.removeChild(link);
                         }
                    }, 1000);
                } else {
                    // Download stopped but not 100% (Error or Cancelled)
                    isDownloading = false;
                    clearInterval(statusInterval);
                }
            }
        } catch (error) {
            console.error('Error polling status:', error);
        }
    }, 1000);
}

function updateStatusUI(data) {
    const progressBar = document.getElementById('progress-bar');
    const statusMessage = document.getElementById('status-message');
    
    progressBar.style.width = data.progress + '%';
    statusMessage.innerText = data.message;
    
    // Try to update title in all possible title elements since we don't know which tab is active easily here
    // or we could track active tab. For now, let's just try to update if empty.
    const platforms = ['youtube', 'facebook', 'tiktok'];
    platforms.forEach(p => {
        const titleElem = document.getElementById(`${p}-title`);
        if (titleElem && data.title && !titleElem.innerText) {
            titleElem.innerText = data.title;
        }
    });
}

async function togglePause() {
    try {
        const response = await fetch('/toggle_pause', { method: 'POST' });
        const data = await response.json();
        document.getElementById('status-message').innerText = data.message;
    } catch (error) {
        console.error('Error:', error);
    }
}

async function openFolder() {
    const folder = document.getElementById('download_folder').value; // Or active tab folder
    const formData = new FormData();
    formData.append('folder_path', folder);
    
    try {
        const response = await fetch('/open_folder', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (!data.success) {
            alert(data.message);
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

async function browseFolder(inputId) {
    try {
        const response = await fetch('/browse_folder', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            document.getElementById(inputId).value = data.path;
        } else if (data.message && data.message !== 'No folder selected') {
            alert(data.message);
        }
    } catch (error) {
        console.error('Error browsing folder:', error);
    }
}
