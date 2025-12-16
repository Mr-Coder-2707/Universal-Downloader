
// --- Instagram New UI/UX Functions ---
let fetchedInstagramMedia = [];

async function fetchInstagramMedia() {
    const url = document.getElementById('instagram-url').value;
    if (!url) {
        alert('Please enter an Instagram URL');
        return;
    }

    const formData = new FormData();
    formData.append('url', url);

    document.getElementById('status-message').innerText = "Fetching Instagram media...";
    document.getElementById('instagram-media-container').style.display = 'none';

    try {
        const response = await fetch('/fetch_instagram_info', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (data.success) {
            fetchedInstagramMedia = data.media;
            renderInstagramMedia(data.media);
            document.getElementById('status-message').innerText = `Found ${data.media.length} media items.`;
        } else {
            alert('Error: ' + data.message);
            document.getElementById('status-message').innerText = "Error fetching info";
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to fetch media');
        document.getElementById('status-message').innerText = "Error fetching info";
    }
}

function renderInstagramMedia(mediaList) {
    const container = document.getElementById('instagram-media-grid');
    container.innerHTML = '';
    
    mediaList.forEach((media, index) => {
        const div = document.createElement('div');
        div.className = 'instagram-media-item';
        div.style.position = 'relative';
        div.style.cursor = 'pointer';
        div.style.border = '2px solid transparent';
        div.style.borderRadius = '8px';
        div.style.overflow = 'hidden';
        div.style.boxShadow = '0 2px 5px rgba(0,0,0,0.1)';
        
        const img = document.createElement('img');
        // Use a proxy to avoid CORS/hotlinking issues
        img.src = `/proxy_image?url=${encodeURIComponent(media.thumbnail)}`; 
        img.style.width = '100%';
        img.style.height = '150px';
        img.style.objectFit = 'cover';
        img.style.display = 'block';
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'media-checkbox';
        checkbox.value = index;
        checkbox.style.position = 'absolute';
        checkbox.style.top = '8px';
        checkbox.style.right = '8px';
        checkbox.style.zIndex = '10';
        checkbox.style.transform = 'scale(1.5)';
        
        div.onclick = (e) => {
            if (e.target !== checkbox) {
                checkbox.checked = !checkbox.checked;
            }
            div.style.border = checkbox.checked ? '2px solid #007bff' : '2px solid transparent';
        };
        
        checkbox.onchange = () => {
             div.style.border = checkbox.checked ? '2px solid #007bff' : '2px solid transparent';
        };

        div.appendChild(img);
        div.appendChild(checkbox);
        
        if (media.type === 'video') {
            const icon = document.createElement('span');
            icon.className = 'material-icons';
            icon.innerText = 'play_circle_filled';
            icon.style.position = 'absolute';
            icon.style.top = '50%';
            icon.style.left = '50%';
            icon.style.transform = 'translate(-50%, -50%)';
            icon.style.color = 'white';
            icon.style.fontSize = '40px';
            icon.style.textShadow = '0 0 5px rgba(0,0,0,0.5)';
            div.appendChild(icon);
        }
        
        container.appendChild(div);
    });
    
    document.getElementById('instagram-media-container').style.display = 'block';
}

async function downloadSelectedInstagram() {
    const checkboxes = document.querySelectorAll('.media-checkbox:checked');
    if (checkboxes.length === 0) {
        alert('Please select at least one item.');
        return;
    }
    
    const selectedIndices = Array.from(checkboxes).map(cb => parseInt(cb.value));
    const selectedUrls = selectedIndices.map(index => fetchedInstagramMedia[index].url);
    
    await downloadInstagramFiles(selectedUrls);
}

async function downloadAllInstagram() {
    if (fetchedInstagramMedia.length === 0) {
        alert('No media to download.');
        return;
    }
    const allUrls = fetchedInstagramMedia.map(m => m.url);
    await downloadInstagramFiles(allUrls);
}

async function downloadInstagramFiles(urls) {
    const folder = document.getElementById('instagram-folder').value;
    
    document.getElementById('status-message').innerText = "Starting download...";
    
    try {
        const response = await fetch('/download_instagram_files', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                urls: urls,
                download_folder: folder
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Start polling for status
            startStatusPolling();
        } else {
            alert('Error: ' + data.message);
            document.getElementById('status-message').innerText = "Download failed";
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Download failed');
    }
}
