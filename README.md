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
- **Project memory** - save and reload project settings (name, client, address, etc.) so you don't have to retype
- **Custom branding** - upload your own logo (JPG/PNG) and enter company contact info; logo appears as photo markers and in the HTML deliverable's "Prepared by" block
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
   - **Authorized JavaScript origins**: add both `http://localhost:24816` and `http://127.0.0.1:24816`
   - **Authorized redirect URIs**: add `http://127.0.0.1:24817`
   - Click **Create**
8. Copy the **Client ID** (looks like `123456789-abc.apps.googleusercontent.com`)
9. In PicPlotter, go to **Settings** and paste it in **Google OAuth Client ID**, click **Save**

### Usage: Browse Drive

1. Click **Import from Drive** → **Browse Drive**
2. Sign into your Google account in the browser window that opens
3. Navigate to and select a folder, click **Select**
4. Photos are imported automatically

### Usage: Paste URL (no OAuth required)

1. Share the Drive folder as "Anyone with the link"
2. Click **Import from Drive**
3. Paste the folder sharing URL and click **Import**

**Web deploys** reference photos by URL - no downloading or re-uploading needed, making deployment fast and lightweight. **Local HTML and KMZ exports** automatically download the photos to produce self-contained files.

## Saved Projects

Save your project settings so you can come back and edit later without retyping.

1. Fill in **Project Name**, **Proposal Link**, **Client**, **Company**, **Address**, etc.
2. Click **Save** — the project appears in the **Saved Projects** dropdown
3. To reload later, select the project from the dropdown and click **Load**
4. To remove a saved project, select it and click **Delete**

Projects are stored locally at `~/.picplotter_auto/projects/`.

## Branding (Logo + Company Info)

Customize PicPlotter with your own logo and company contact info. These settings are global — set once and used across every project.

1. In **Options → Settings**, scroll to the **Company Logo** section
2. Click **Upload Logo** and pick a JPG or PNG (logo is auto-resized to 512px and saved to `~/.picplotter_auto/logo.png`)
3. Fill in **Company Name**, **Company Address**, **Phone Number**, and (optionally) **Company Website** — values save automatically when you click out of each field
4. Click **Reset to Default** any time to revert to the bundled fallback

Where the branding shows up:
- **Photo markers** — each pin uses your logo with a colored rectangular outline that identifies the photo group. The logo's own colors are preserved; only the outline color changes per group. Default group uses a black outline.
- **Marker numbers** — sit in a small white badge in the lower-right of each marker so they remain readable against any logo.
- **HTML deliverable sidebar** — your logo replaces the default header logo, and a **Prepared by** block renders below the client info with your company name, address, phone, and website (rendered as a clickable link).

Tips:
- Best results: high-contrast, mostly single-color logos on a white or transparent background.
- Logo changes apply to new exports and the next time the map editor is opened.
- Website URLs without `http://` or `https://` get `https://` prepended automatically.

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
- Check that `http://127.0.0.1:24817` is in **Authorized redirect URIs**
- Check that both `http://localhost:24816` and `http://127.0.0.1:24816` are in **Authorized JavaScript origins**
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
