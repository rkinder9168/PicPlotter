# PicPlotter Auto

Auto-plot Google satellite imagery from your geotagged photos, then export KMZ or HTML deliverables.

**Single-window dark-themed UI** built in pywebview for a seamless workflow.

## Quick Start

1. Double-click `PicPlotterAuto.exe`
2. (Optional) Enter your Google Maps API key on the main screen and click \"Save\"
3. Click \"Select Photos\" and choose your images
4. Click "Open Map Editor" to load the tile preview and markers
5. Adjust marker size, drag markers, and rotate the view if needed
6. Export the HTML deliverable from the map editor

## Features

- **Single-window map workflow** - no popups, editor opens inside the same app window
- **Google satellite editor** - tile preview matches export, rotate, pan, and adjust markers live
- **Manual marker corrections** - drag markers to fine-tune placement
- **Manual placement for any photo** - click the map to place non-GPS photos
- **KMZ and HTML outputs** - Google Earth Pro and client-ready HTML
- **Deploy to Web** - instantly deploy interactive maps to Netlify and share a link with clients
- **Modern dark UI** - single-window experience
- **Supports HEIC and JPG** - works with iPhone and Android photos

## Requirements

- Windows 10 or 11
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

## Building from Source

```bash
# Install dependencies
pip install -r requirements.txt

# Build executable
python build/build.py
```

The executable will be created in the `dist` folder.

## Windows Dev Helpers

If you develop in WSL but run on Windows, these scripts sync and run the app:

```powershell
scripts\sync_windows.ps1
scripts\run_windows.ps1
```

Both scripts default to `\\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_auto_gpt`
and `C:\dev\PicPlotter_auto_gpt`. Edit the paths at the top if needed.

## License

MIT License - free for personal and commercial use.

---

Created with PicPlotter Auto
