from flask import Flask, render_template, request, jsonify, send_from_directory, Response
import yt_dlp
import os
import threading
import time
from werkzeug.utils import secure_filename
import sys
import subprocess
import requests # Add this import
import uuid
import shutil
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TDRC, TCON, TRCK, TPE2, TPE3
from mutagen.id3._util import ID3NoHeaderError
from mutagen import File
import io
import instaloader
import re

# Set environment variables for Vercel/Serverless to use /tmp for caching
if os.environ.get('VERCEL'):
    os.environ['XDG_CACHE_HOME'] = '/tmp/.cache'
    os.environ['XDG_CONFIG_HOME'] = '/tmp/.config'
    os.environ['MPLCONFIGDIR'] = '/tmp/.matplotlib'

# Common User Agent to bypass bot detection
COMMON_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

app = Flask(__name__)

# --- Configuration ---
# Check if running on Vercel or similar environment
if os.environ.get('VERCEL') or not os.path.exists('D:/'):
    app.config['DOWNLOAD_FOLDER'] = '/tmp/downloads'
else:
    app.config['DOWNLOAD_FOLDER'] = 'D:/Universal Video Downloader Downloads'

app.config['ALLOWED_EXTENSIONS'] = {'mp4', 'mp3', 'webm'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# --- Global Variables ---
download_status = {
    'is_paused': False,
    'is_downloading': False,
    'progress': 0,
    'current_file': None,
    'message': 'Ready to download',
    'title': '',
    'download_thread': None
}

# Generate a unique ID for the device
DEVICE_ID_FILE = os.path.join(app.config['DOWNLOAD_FOLDER'], 'device_id.txt')
def get_device_id():
    try:
        if not os.path.exists(app.config['DOWNLOAD_FOLDER']):
            os.makedirs(app.config['DOWNLOAD_FOLDER'])
            
        if not os.path.exists(DEVICE_ID_FILE):
            device_id = str(uuid.uuid4())
            with open(DEVICE_ID_FILE, 'w') as f:
                f.write(device_id)
        else:
            with open(DEVICE_ID_FILE, 'r') as f:
                device_id = f.read().strip()
        return device_id
    except Exception as e:
        print(f"Error getting device ID: {e}")
        return "unknown-device-id"

DEVICE_ID = get_device_id()

# --- Helper Functions ---
def get_ffmpeg_location():
    """
    Find ffmpeg location with fallback options
    """
    # First check if ffmpeg is in PATH
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return os.path.dirname(ffmpeg_path)
    
    # Common Windows ffmpeg locations as fallback
    common_paths = [
        r"C:\ffmpeg\bin",  # Found location!
        r"C:\ffmpeg-8.0-essentials_build\bin",
        r"C:\Users\MAHMOUD SABRY\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
        r"C:\Program Files (x86)\ffmpeg\bin",
    ]
    
    for path in common_paths:
        if os.path.exists(os.path.join(path, 'ffmpeg.exe')):
            print(f"✅ Found ffmpeg at: {path}")  # للـ debugging
            return path
    
    print("❌ ffmpeg not found in any expected location")  # للـ debugging
    return None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def secure_path(path):
    # Normalize the path to resolve any ".." components
    normalized_path = os.path.normpath(path)
    # Check if the path is within the intended download directory
    if os.path.commonprefix((normalized_path, os.path.abspath(app.config['DOWNLOAD_FOLDER']))) != os.path.abspath(app.config['DOWNLOAD_FOLDER']):
        raise ValueError("Invalid download path specified.")
    return normalized_path

def create_download_folder():
    if not os.path.exists(app.config['DOWNLOAD_FOLDER']):
        os.makedirs(app.config['DOWNLOAD_FOLDER'])
        # Create first run file
        with open(os.path.join(app.config['DOWNLOAD_FOLDER'], 'first_run.txt'), 'w') as f:
            f.write("This file indicates the program was run for the first time.\n")

def get_available_formats():
    return ['Video', 'Audio']

def get_available_qualities():
    return ['144p', '240p', '360p', '480p', '720p', '1080p', '1440p', '2160p']

def add_metadata_to_audio(file_path, video_info, thumbnail_data=None):
    """
    Add metadata to audio file using information from video_info
    """
    try:
        # Load the audio file
        audio_file = MP3(file_path, ID3=ID3)
        
        # Try to load existing tags, if not create new ones
        try:
            audio_file.add_tags()
        except ID3NoHeaderError:
            pass
        
        # Extract information from video_info
        title = video_info.get('title', '')
        uploader = video_info.get('uploader', '') or video_info.get('artist', '') or video_info.get('creator', '')
        album = video_info.get('album', '') or video_info.get('playlist_title', '') or uploader
        upload_date = video_info.get('upload_date', '')
        description = video_info.get('description', '')
        
        # Format upload date
        if upload_date and len(upload_date) >= 4:
            year = upload_date[:4]
        else:
            year = ''
        
        # Set basic metadata
        if title:
            audio_file.tags.add(TIT2(encoding=3, text=title))  # Title
        
        if uploader:
            audio_file.tags.add(TPE1(encoding=3, text=uploader))  # Artist
            audio_file.tags.add(TPE2(encoding=3, text=uploader))  # Album Artist
        
        if album:
            audio_file.tags.add(TALB(encoding=3, text=album))  # Album
        
        if year:
            audio_file.tags.add(TDRC(encoding=3, text=year))  # Year
        
        # Try to determine genre from title or description
        genre = determine_genre(title, description)
        if genre:
            audio_file.tags.add(TCON(encoding=3, text=genre))  # Genre
        
        # Add track number (default to 1)
        audio_file.tags.add(TRCK(encoding=3, text="1"))
        
        # Add thumbnail as album art if available
        if thumbnail_data:
            audio_file.tags.add(APIC(
                encoding=3,
                mime='image/jpeg',
                type=3,  # Cover (front)
                desc='Cover',
                data=thumbnail_data
            ))
        
        # Save the changes
        audio_file.save()
        print(f"✅ Metadata added to: {file_path}")
        
    except Exception as e:
        print(f"❌ Error adding metadata to {file_path}: {str(e)}")

def determine_genre(title, description):
    """
    Try to determine genre based on title and description
    """
    title_lower = title.lower() if title else ''
    desc_lower = description.lower() if description else ''
    
    # Common Arabic music genres
    if any(word in title_lower or word in desc_lower for word in ['أغنية', 'أغاني', 'موسيقى', 'مهرجان', 'شعبي']):
        return 'Arabic Pop'
    elif any(word in title_lower or word in desc_lower for word in ['راب', 'rap', 'hip hop']):
        return 'Arabic Rap'
    elif any(word in title_lower or word in desc_lower for word in ['كلاسيكي', 'طرب', 'أم كلثوم', 'فيروز']):
        return 'Arabic Classical'
    elif any(word in title_lower or word in desc_lower for word in ['مهرجان', 'شعبي']):
        return 'Mahraganat'
    elif any(word in title_lower or word in desc_lower for word in ['pop', 'بوب']):
        return 'Pop'
    elif any(word in title_lower or word in desc_lower for word in ['rock', 'روك']):
        return 'Rock'
    elif any(word in title_lower or word in desc_lower for word in ['jazz', 'جاز']):
        return 'Jazz'
    elif any(word in title_lower or word in desc_lower for word in ['classical', 'كلاسيكي']):
        return 'Classical'
    else:
        return 'Music'  # Default genre

# --- Download Functions ---
def progress_hook(d):
    if download_status['is_paused']:
        raise Exception("Download paused")
    
    if d['status'] == 'downloading':
        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
        downloaded_bytes = d.get('downloaded_bytes')
        if total_bytes and downloaded_bytes:
            percentage = (downloaded_bytes / total_bytes) * 100
            download_status['progress'] = percentage
            download_status['message'] = f"Downloading... {percentage:.1f}%"
    
    elif d['status'] == 'finished':
        download_status['progress'] = 100
        download_status['message'] = "Finalizing..."
    
    elif d['status'] == 'error':
        download_status['message'] = "Error occurred during download"

def download_video(url, quality, mode, download_folder, platform=None):
    global download_status
    
    try:
        download_status.update({
            'is_downloading': True,
            'is_paused': False,
            'progress': 0,
            'message': 'Starting download...',
            'current_file': None
        })
        
        processed_quality = quality[:-1] if quality.endswith('p') else quality
        
        # Use the title from download_status if available, otherwise fallback to yt-dlp's title
        if download_status.get('title'):
            # Sanitize the title to be used as a filename
            sanitized_title = secure_filename(download_status['title'])
            outtmpl_path = os.path.join(download_folder, f'{sanitized_title}.%(ext)s')
        else:
            outtmpl_path = os.path.join(download_folder, '%(title)s.%(ext)s')

        ydl_opts_base = {
            'outtmpl': outtmpl_path,
            'noplaylist': True,
            'progress_hooks': [progress_hook],
            'postprocessors': [],
            'quiet': True,
            'merge_output_format': 'mp4',
            'compat_options': ['no-sabr'],
            'restrictfilenames': True,
            'writeinfojson': True,  # Save video info for metadata
            'user_agent': COMMON_USER_AGENT,
            'nocheckcertificate': True,
        }
        
        # Add ffmpeg location if available
        ffmpeg_location = get_ffmpeg_location()
        if ffmpeg_location:
            ydl_opts_base['ffmpeg_location'] = ffmpeg_location
            print(f"🎯 Using ffmpeg from: {ffmpeg_location}")
        else:
            print("⚠️ ffmpeg not found - download quality may be limited")

        if mode == "Audio":
            ydl_opts = ydl_opts_base.copy()
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['writethumbnail'] = True
            ydl_opts['postprocessors'].append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            })
            ydl_opts['postprocessors'].append({
                'key': 'EmbedThumbnail',
            })
            if download_status.get('title'):
                sanitized_title = secure_filename(download_status['title'])
                ydl_opts['outtmpl'] = os.path.join(download_folder, f'{sanitized_title}.mp3')
            else:
                ydl_opts['outtmpl'] = os.path.join(download_folder, '%(title)s.mp3')
        else:  # Video
            ydl_opts = ydl_opts_base.copy()

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            download_status['message'] = 'Extracting video information...'
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if mode == "Audio":
                # Get the actual output filename after conversion
                base_filename = os.path.splitext(filename)[0]
                mp3_filename = base_filename + '.mp3'
                
                # Check if the file exists with different possible names
                possible_files = [
                    mp3_filename,
                    filename.replace('.webm', '.mp3').replace('.m4a', '.mp3'),
                    os.path.join(download_folder, os.path.basename(base_filename) + '.mp3')
                ]
                
                actual_file = None
                for possible_file in possible_files:
                    if os.path.exists(possible_file):
                        actual_file = possible_file
                        break
                
                if actual_file:
                    filename = actual_file
                    
                    # Add metadata to audio file
                    download_status['message'] = 'Adding metadata...'
                    
                    # Download thumbnail data for album art
                    thumbnail_data = None
                    if info.get('thumbnail'):
                        try:
                            thumbnail_response = requests.get(info['thumbnail'], timeout=10)
                            if thumbnail_response.status_code == 200:
                                thumbnail_data = thumbnail_response.content
                        except Exception as e:
                            print(f"⚠️ Could not download thumbnail: {e}")
                    
                    # Add metadata to the audio file
                    add_metadata_to_audio(filename, info, thumbnail_data)
                    
                    # Clean up info.json file if it exists
                    info_json_path = os.path.splitext(filename)[0] + '.info.json'
                    if os.path.exists(info_json_path):
                        os.remove(info_json_path)
                else:
                    print(f"⚠️ Could not find converted audio file. Expected: {mp3_filename}")
            
            download_status['current_file'] = os.path.basename(filename)
            download_status['message'] = "Download complete!"
            download_status['progress'] = 100

    except Exception as e:
        error_message = str(e).splitlines()[0]
        if "Download paused" in error_message:
            download_status['message'] = "Download paused"
        else:
            download_status['message'] = f"Error: {error_message}"
    finally:
        download_status['is_downloading'] = False

@app.route('/download_thumbnail_proxy')
def download_thumbnail_proxy():
    thumbnail_url = request.args.get('url')
    if not thumbnail_url:
        return "Missing URL parameter", 400

    try:
        response = requests.get(thumbnail_url, stream=True)
        response.raise_for_status() # Raise an exception for bad status codes

        # Get the content type from the original response
        content_type = response.headers.get('content-type', 'image/jpeg')

        # Create a streaming response to send to the client
        return Response(response.iter_content(chunk_size=8192),
                        content_type=content_type,
                        headers={"Content-Disposition": "attachment; filename=thumbnail.jpg"})

    except requests.exceptions.RequestException as e:
        return str(e), 500

# --- Routes ---
@app.route('/')
def index():
    create_download_folder()
    return render_template('index.html', 
                         formats=get_available_formats(),
                         qualities=get_available_qualities(),
                         default_folder=app.config['DOWNLOAD_FOLDER'])

@app.route('/fetch_title', methods=['POST'])
def fetch_title():
    url = request.form.get('url')
    if not url:
        return jsonify({'success': False, 'title': 'Please enter a video URL', 'thumbnail': None})
    
    try:
        ydl_opts = {
            'quiet': True,
            'extract_flat': 'in_playlist',
            'force_generic_extractor': True,
            'user_agent': COMMON_USER_AGENT,
            'nocheckcertificate': True,
            'ignoreerrors': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return jsonify({'success': False, 'title': 'Could not fetch video info', 'thumbnail': None})
                
            title = info.get('title', 'No title found')
            thumbnail = info.get('thumbnail', None)
            download_status['title'] = title
            return jsonify({'success': True, 'title': title, 'thumbnail': thumbnail})
    except Exception as e:
        return jsonify({'success': False, 'title': f'Error fetching title: {str(e)}', 'thumbnail': None})

@app.route('/start_download', methods=['POST'])
def start_download():
    global download_status
    
    url = request.form.get('url')
    quality = request.form.get('quality')
    mode = request.form.get('mode')
    download_folder = request.form.get('download_folder')
    platform = request.form.get('platform')
    
    if not url:
        return jsonify(success=False, message='URL is required')

    try:
        download_folder = secure_path(download_folder)
    except ValueError as e:
        return jsonify(success=False, message=str(e))

    if platform != 'other':
        try:
            ydl_opts = {
                'quiet': True,
                'extract_flat': 'in_playlist',
                'force_generic_extractor': True,
                'user_agent': COMMON_USER_AGENT,
                'nocheckcertificate': True,
                'ignoreerrors': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    extractor = info.get('extractor_key', '').lower()
                    if platform.lower() not in extractor:
                        # Just a warning, don't block
                        print(f"Warning: URL might not be a valid {platform} link. Extractor: {extractor}")
        except Exception as e:
            print(f"Error verifying URL: {str(e)}")
            # Continue anyway, don't block download on verification error

    if download_status['is_downloading']:
        return jsonify(success=False, message='Another download is already in progress')
    
    download_status['download_thread'] = threading.Thread(
        target=download_video, 
        args=(url, quality, mode, download_folder, platform)
    )
    download_status['download_thread'].start()
    
    return jsonify(success=True)


@app.route('/download_thumbnail', methods=['POST'])
def download_thumbnail():
    url = request.form.get('url')
    download_folder = request.form.get('download_folder', app.config['DOWNLOAD_FOLDER'])

    if not url:
        return jsonify(success=False, message='URL is required')

    try:
        ydl_opts = {
            'writethumbnail': True,
            'skip_download': True,
            'outtmpl': os.path.join(download_folder, '%(title)s.%(ext)s'),
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegThumbnailsConvertor',
                'format': 'jpg',
            }],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)
        
        return jsonify(success=True, message='Thumbnail downloaded successfully!')
    except Exception as e:
        return jsonify(success=False, message=f'Error downloading thumbnail: {str(e)}')


@app.route('/toggle_pause', methods=['POST'])
def toggle_pause():
    download_status['is_paused'] = not download_status['is_paused']
    if download_status['is_paused']:
        return jsonify({'success': True, 'is_paused': True, 'message': 'Download paused'})
    else:
        return jsonify({'success': True, 'is_paused': False, 'message': 'Download resumed'})

@app.route('/get_status', methods=['GET'])
def get_status():
    return jsonify({
        'is_downloading': download_status['is_downloading'],
        'is_paused': download_status['is_paused'],
        'progress': download_status['progress'],
        'message': download_status['message'],
        'current_file': download_status['current_file'],
        'title': download_status['title']
    })

@app.route('/browse_folder', methods=['POST'])
def browse_folder():
    try:
        # Run a subprocess to open the dialog to avoid thread issues with Flask/Tkinter
        cmd = [sys.executable, '-c', "import tkinter as tk, tkinter.filedialog as fd; root=tk.Tk(); root.withdraw(); root.attributes('-topmost', True); print(fd.askdirectory())"]
        
        # Use creationflags to hide the console window on Windows if needed, but for now standard is fine
        result = subprocess.check_output(cmd).decode('utf-8').strip()
        
        if result:
            # Normalize path
            result = os.path.normpath(result)
            return jsonify({'success': True, 'path': result})
        else:
            return jsonify({'success': False, 'message': 'No folder selected'})
    except Exception as e:
        print(f"Error browsing folder: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/open_folder', methods=['POST'])
def open_folder():
    folder_path = request.form.get('folder_path', app.config['DOWNLOAD_FOLDER'])
    if not os.path.isdir(folder_path):
        return jsonify({'success': False, 'message': 'Folder not found'})
    
    try:
        if os.name == 'nt':  # Windows
            os.startfile(folder_path)
        elif os.name == 'posix':  # macOS and Linux
            if sys.platform == 'darwin':
                subprocess.run(['open', folder_path])
            else:
                subprocess.run(['xdg-open', folder_path])
        return jsonify({'success': True, 'message': 'Folder opened'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Could not open folder: {str(e)}'})

@app.route('/downloads/<filename>')
def download_file(filename):
    return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/get_device_id', methods=['GET'])
def get_device_id_route():
    return jsonify({'device_id': DEVICE_ID})

# --- Instagram Download Functions ---
def download_instagram_media(url, download_folder):
    """
    Download photos/videos from Instagram posts, reels, or stories
    """
    try:
        # Create an Instaloader instance
        L = instaloader.Instaloader(
            download_pictures=True,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            dirname_pattern=download_folder,
            filename_pattern='{date_utc}_UTC_{typename}',
        )
        
        # Extract shortcode from URL
        shortcode = extract_instagram_shortcode(url)
        if not shortcode:
            return {'success': False, 'message': 'Invalid Instagram URL'}
        
        # Get the post
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        
        # Download the post
        L.download_post(post, target=download_folder)
        
        # Get downloaded files
        downloaded_files = []
        for file in os.listdir(download_folder):
            if file.startswith(post.date_utc.strftime('%Y-%m-%d_%H-%M-%S')):
                downloaded_files.append(file)
        
        return {
            'success': True, 
            'message': f'Downloaded {len(downloaded_files)} file(s) successfully!',
            'files': downloaded_files,
            'caption': post.caption if post.caption else 'No caption'
        }
        
    except Exception as e:
        return {'success': False, 'message': f'Error: {str(e)}'}

def fetch_instagram_media_info(url):
    try:
        L = instaloader.Instaloader()
        shortcode = extract_instagram_shortcode(url)
        if not shortcode:
            return {'success': False, 'message': 'Invalid Instagram URL'}
        
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        
        media_list = []
        
        if post.typename == 'GraphSidecar':
            for node in post.get_sidecar_nodes():
                if node.is_video:
                    media_list.append({
                        'type': 'video',
                        'url': node.video_url,
                        'thumbnail': node.display_url,
                        'shortcode': shortcode
                    })
                else:
                    media_list.append({
                        'type': 'image',
                        'url': node.display_url,
                        'thumbnail': node.display_url,
                        'shortcode': shortcode
                    })
        elif post.is_video:
            media_list.append({
                'type': 'video',
                'url': post.video_url,
                'thumbnail': post.url,
                'shortcode': shortcode
            })
        else:
            media_list.append({
                'type': 'image',
                'url': post.url,
                'thumbnail': post.url,
                'shortcode': shortcode
            })
            
        return {'success': True, 'media': media_list}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def extract_instagram_shortcode(url):
    """
    Extract shortcode from various Instagram URL formats
    """
    patterns = [
        r'instagram\.com/p/([^/?]+)',
        r'instagram\.com/reel/([^/?]+)',
        r'instagram\.com/tv/([^/?]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

@app.route('/download_instagram', methods=['POST'])
def download_instagram():
    url = request.form.get('url')
    download_folder = request.form.get('download_folder', app.config['DOWNLOAD_FOLDER'])
    
    if not url:
        return jsonify({'success': False, 'message': 'URL is required'})
    
    # Verify it's an Instagram URL
    if 'instagram.com' not in url:
        return jsonify({'success': False, 'message': 'Please provide a valid Instagram URL'})
    
    try:
        download_folder = secure_path(download_folder)
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)})
    
    # Download in a separate thread to avoid blocking
    def download_thread():
        result = download_instagram_media(url, download_folder)
        # Store result for the next status check
        download_status['instagram_result'] = result
    
    thread = threading.Thread(target=download_thread)
    thread.start()
    thread.join()  # Wait for download to complete
    
    return jsonify(download_status.get('instagram_result', {'success': False, 'message': 'Download failed'}))

@app.route('/fetch_instagram_info', methods=['POST'])
def fetch_instagram_info_route():
    url = request.form.get('url')
    if not url:
        return jsonify({'success': False, 'message': 'URL is required'})
    
    result = fetch_instagram_media_info(url)
    return jsonify(result)

@app.route('/download_instagram_files', methods=['POST'])
def download_instagram_files():
    data = request.json
    urls = data.get('urls', [])
    download_folder = data.get('download_folder', app.config['DOWNLOAD_FOLDER'])
    
    if not urls:
        return jsonify({'success': False, 'message': 'No files selected'})

    def download_task():
        global download_status
        download_status['is_downloading'] = True
        download_status['progress'] = 0
        download_status['message'] = 'Starting download...'
        
        try:
            safe_download_folder = secure_path(download_folder)
            if not os.path.exists(safe_download_folder):
                os.makedirs(safe_download_folder)
                
            total_files = len(urls)
            downloaded_count = 0
            
            for i, url in enumerate(urls):
                download_status['message'] = f'Downloading file {i+1} of {total_files}'
                download_status['progress'] = int((i / total_files) * 100)
                
                # Determine extension
                ext = 'jpg'
                if 'mp4' in url:
                    ext = 'mp4'
                
                filename = f"instagram_{int(time.time())}_{downloaded_count}.{ext}"
                
                # Use requests to download
                try:
                    response = requests.get(url, stream=True)
                    if response.status_code == 200:
                        file_path = os.path.join(safe_download_folder, filename)
                        with open(file_path, 'wb') as f:
                            for chunk in response.iter_content(1024):
                                f.write(chunk)
                        downloaded_count += 1
                except Exception as e:
                    print(f"Error downloading {url}: {e}")
                    
            download_status['progress'] = 100
            download_status['message'] = f'Downloaded {downloaded_count} files successfully.'
            
        except Exception as e:
            download_status['message'] = f'Error: {str(e)}'
        finally:
            download_status['is_downloading'] = False

    thread = threading.Thread(target=download_task)
    thread.start()
        
    return jsonify({'success': True, 'message': 'Download started'})

@app.route('/download_instagram_single', methods=['POST'])
def download_instagram_single():
    """Download a single media item from Instagram"""
    media_url = request.form.get('media_url')
    media_type = request.form.get('media_type', 'image')
    download_folder = request.form.get('download_folder', app.config['DOWNLOAD_FOLDER'])
    
    if not media_url:
        return jsonify({'success': False, 'message': 'Media URL is required'})
    
    try:
        download_folder = secure_path(download_folder)
        
        # Generate filename
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        ext = 'mp4' if media_type == 'video' else 'jpg'
        filename = f'instagram_{timestamp}.{ext}'
        filepath = os.path.join(download_folder, filename)
        
        # Download the media
        response = requests.get(media_url, stream=True)
        response.raise_for_status()
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return jsonify({
            'success': True,
            'message': 'Media downloaded successfully!',
            'filename': filename
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error downloading media: {str(e)}'})

@app.route('/proxy_image')
def proxy_image():
    url = request.args.get('url')
    if not url:
        return "URL required", 400
    
    try:
        # Fetch the image from the external URL
        resp = requests.get(url, stream=True)
        
        # Pass along the content type and the content
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in resp.raw.headers.items()
                   if name.lower() not in excluded_headers]
        
        return Response(resp.content, resp.status_code, headers)
    except Exception as e:
        return str(e), 500

# --- Main ---
if __name__ == '__main__':
    create_download_folder()
    app.run(debug=True, host='0.0.0.0', port=5000)
