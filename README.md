# PicPlotter Auto

Auto-plot Google satellite imagery from your geotagged photos, then export KMZ or HTML deliverables.

**Single-window dark-themed UI** built in pywebview for a seamless workflow.

## Quick Start

1. Double-click `PicPlotterAuto.exe`
2. (Optional) Enter your Google Maps API key on the main screen and click "Save"
3. Click "Import Photos" to select local images, or "Import from Drive" to load from a shared Google Drive folder
4. Click "Open Map Editor" to load the tile preview and markers
5. Adjust marker size, drag markers, and rotate the view if needed
6. Export the HTML deliverable from the map editor

## Features

- **Single-window map workflow** - no popups, editor opens inside the same app window
- **Google satellite editor** - tile preview matches export, rotate, pan, and adjust markers live
- **Manual marker corrections** - drag markers to fine-tune placement
- **Manual placement for any photo** - click the map to place non-GPS photos
- **Google Drive import** - load photos from a shared Drive folder; web deploys reference images by URL (no download/re-upload)
- **KMZ and HTML outputs** - Google Earth Pro and client-ready HTML
- **Deploy to Web** - instantly deploy interactive maps to Netlify and share a link with clients
- **Modern dark UI** - single-window experience
- **Supports HEIC and JPG** - works with iPhone and Android photos

## Requirements

- Windows 10 or 11 (macOS also supported)
- Google Earth Pro (free) to view KMZ files
- Photos with GPS location data (taken with location services enabled)
- Google Maps API key (optional, recommended for editor tile access)
- Internet connection for the map editor
- WebView2 Runtime (usually preinstalled on Windows 10/11)
- If running from source on Windows: `pythonnet` installed (`pip install pythonnet`)

## API Key Setup

PicPlotter Auto can use a Google Maps API key to fetch editor tiles.

- Enter the key on the main PicPlotter screen and click "Save".
- The key is stored at `~/.picplotter_auto/config.json`.
- You can also set `GOOGLE_MAPS_API_KEY` as an environment variable.

## Google Drive Import

Import photos directly from a Google Drive folder instead of downloading them first. Two options:

- **Browse Drive** — sign into Google and pick a folder (recommended)
- **Paste URL** — paste a shared folder link (folder must be public)

### One-Time Setup: Google Drive API

1. Go to [Google Cloud Console](https://console.cloud.google.com) → select your project (same one as your Maps API key)
2. Go to **APIs & Services → Library**
3. Search for **Google Drive API** and click **Enable**
4. If your API key has restrictions, go to **APIs & Services → Credentials**, click your API key, and add **Google Drive API** to the allowed APIs

### One-Time Setup: Browse Drive (OAuth + Picker)

This lets you sign into Google and browse your Drive folders directly from PicPlotter — no URL copying needed.

1. Go to [Google Cloud Console](https://console.cloud.google.com) → select your project
2. Go to **APIs & Services → Library**
3. Search for **Google Picker API** and click **Enable**
4. Go to **APIs & Services → Credentials**
5. Click **+ Create Credentials → OAuth client ID**
6. If prompted to configure the OAuth consent screen:
   - Choose **External** user type, click **Create**
   - Fill in the required fields (App name, User support email, Developer contact email)
   - Click **Save and Continue** through the remaining steps
   - On the **Publishing status** page, you can leave it in "Testing" — add your Google account as a test user
7. Back on the **Create OAuth client ID** page:
   - Application type: **Web application**
   - Name: anything (e.g. "PicPlotter")
   - **Authorized JavaScript origins**: add `http://localhost:24816`
   - **Authorized redirect URIs**: add `http://localhost:24816`
   - Click **Create**
8. Copy the **Client ID** (looks like `123456789-abc.apps.googleusercontent.com`)
9. In PicPlotter, go to **Settings** and paste it in **Google OAuth Client ID**, click **Save**

### Usage: Browse Drive

1. Click **Import from Drive** → **Browse Drive**
2. Sign into your Google account in the popup
3. Navigate to and select a folder, click **Select**
4. Photos are imported automatically

### Usage: Paste URL (no OAuth required)

1. Share the Drive folder as "Anyone with the link"
2. Click **Import from Drive**
3. Paste the folder sharing URL and click **Import**

**Web deploys** reference photos by URL - no downloading or re-uploading needed, making deployment fast and lightweight. **Local HTML and KMZ exports** automatically download the photos to produce self-contained files.

## Deploy to Web (Netlify)

Share interactive maps with clients via a simple link instead of email attachments.

### One-Time Setup

1. Create a free Netlify account at [netlify.com](https://www.netlify.com)
2. Go to [app.netlify.com/user/applications/personal](https://app.netlify.com/user/applications/personal) and create a personal access token
3. In PicPlotter, go to Options and paste the token in "Netlify Token", then click Save
4. Deploy your first map using "Deploy to Web"

### Usage

After setup, click "Deploy to Web" in the map editor to get a shareable URL like:
`https://picplotter-maps.netlify.app`

Send this link to clients - they can view the interactive map directly in their browser without downloading anything.

## How It Works

PicPlotter Auto reads the GPS coordinates from your photos and opens a tile-based satellite
map editor inside the same window. Adjust markers, size, and rotation as needed. The editor exports a single
offline HTML file with a high-resolution map snapshot (no API key required).

## HTML Map Export

Create professional, interactive HTML deliverables for clients:

1. Select photos (GPS or non-GPS)
2. Click "Open Map Editor" and GPS markers appear automatically
3. Click the map to place untagged photos, drag markers to adjust, and set marker size or rotation
4. Click "Export Interactive Image" to generate the HTML map

The HTML map features:
- Interactive pan and zoom
- Clickable markers with photo lightbox
- Adjustable marker size with live preview
- Single offline HTML output (no API key required)

## Supported Photo Formats

- **JPG/JPEG** - standard camera photos
- **HEIC/HEIF** - iPhone photos (if pillow-heif is installed)

## Tips

- Make sure your phone's location services are enabled when taking photos
- For photos without GPS data, place markers manually in the map editor
- Higher quality settings create larger files but better-looking images
- You can select multiple photos at once (Ctrl+Click or Shift+Click)

## Troubleshooting

**"No GPS data" message**
- The photo doesn't have location information embedded
- Make sure location services were enabled when the photo was taken

**Map won't load**
- Verify the Google Maps API key is correct (if used)
- Check internet connectivity

**Photos don't appear in Google Earth**
- In Google Earth Pro: Tools -> Options -> General
- Enable "Allow placemark balloons to access local data"

**Drive import fails (URL paste)**
- Ensure the folder is shared as "Anyone with the link"
- Verify the Google Drive API is enabled on your Cloud project
- Check that your API key restrictions allow the Drive API

**Browse Drive shows "redirect_uri_mismatch" or sign-in error**
- Verify your OAuth Client ID is a **Web application** type (not Desktop)
- Check that `http://localhost:24816` is in both **Authorized JavaScript origins** and **Authorized redirect URIs**
- If your app is in "Testing" mode, make sure your Google account is added as a test user
- Wait a few minutes after making changes — Google can take time to propagate

## Building from Source

```bash
# Install dependencies
pip install -r requirements.txt

# Build executable
python build/build.py
```

The executable will be created in the `dist` folder.

## CI/CD

The GitHub Actions workflow (`.github/workflows/build.yml`) builds Windows and macOS installers on manual dispatch:

1. Go to the repo's **Actions** tab
2. Click **Build Installers** -> **Run workflow**
3. Download installers from the created GitHub Release

## License

MIT License - free for personal and commercial use.

---

Created with PicPlotter Auto
