"""
PicPlotter Auto Build Script

Creates a standalone executable using PyInstaller.
Works on Windows, Linux, and macOS.
"""

import subprocess
import sys
import shutil
import platform
from pathlib import Path

# Configuration
APP_NAME = "PicPlotterAuto"
PLATFORM = platform.system()  # 'Windows', 'Linux', or 'Darwin'

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build_temp"


def read_version() -> str:
    """Read the app version from src/__init__.py."""
    version_path = SRC_DIR / "__init__.py"
    if not version_path.exists():
        return "0.0.0"
    for line in version_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("__version__"):
            _, raw_value = line.split("=", 1)
            return raw_value.strip().strip('"').strip("'")
    return "0.0.0"


VERSION = read_version()


def clean():
    """Remove previous build artifacts."""
    print("Cleaning previous builds...")

    for dir_path in [DIST_DIR, BUILD_DIR]:
        if dir_path.exists():
            shutil.rmtree(dir_path)

    # Remove spec file
    spec_file = PROJECT_ROOT / f"{APP_NAME}.spec"
    if spec_file.exists():
        spec_file.unlink()


def build_executable():
    """Build the executable using PyInstaller."""
    print(f"Building {APP_NAME} v{VERSION}...")

    main_script = SRC_DIR / "main.py"

    # PyInstaller arguments
    args = [
        sys.executable, "-m", "PyInstaller",
        str(main_script),
        f"--name={APP_NAME}",
        "--windowed",          # No console window
        "--clean",             # Clean cache
        f"--distpath={DIST_DIR}",
        f"--workpath={BUILD_DIR}",
        f"--specpath={PROJECT_ROOT}",
        # Hidden imports for pillow-heif
        "--hidden-import=pillow_heif",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--hidden-import=PIL.ExifTags",
        # Hidden imports for pywebview
        "--hidden-import=webview",
        # Hidden imports for src modules
        "--hidden-import=src",
        "--hidden-import=src.exif_extractor",
        "--hidden-import=src.image_processor",
        "--hidden-import=src.kmz_generator",
        "--hidden-import=src.html_map_generator",
        "--hidden-import=src.config",
        "--hidden-import=src.coordinate_transform",
        "--hidden-import=src.utils",
        "--hidden-import=src.netlify_deployer",
        "--hidden-import=src.marker_utils",
        "--hidden-import=src.photo_groups",
        "--hidden-import=src.google_drive",
    ]
    if PLATFORM == "Darwin":
        args.append("--onedir")
    else:
        args.append("--onefile")  # Single executable on Windows/Linux

    # Prefer platform-appropriate icon assets.
    icon_path = None
    if PLATFORM == "Darwin":
        mac_icon = PROJECT_ROOT / "assets" / "icon.icns"
        if mac_icon.exists():
            icon_path = mac_icon
    if icon_path is None:
        icon_path = PROJECT_ROOT / "assets" / "favicon_everline1.ico"
        if not icon_path.exists():
            icon_path = PROJECT_ROOT / "assets" / "icon.ico"
            if not icon_path.exists():
                marker_icon = PROJECT_ROOT / "assets" / "marker_ev.png"
                if marker_icon.exists():
                    try:
                        from PIL import Image
                        with Image.open(marker_icon) as img:
                            img = img.convert("RGBA")
                            max_side = max(img.size)
                            square = Image.new("RGBA", (max_side, max_side), (0, 0, 0, 0))
                            offset = ((max_side - img.size[0]) // 2, (max_side - img.size[1]) // 2)
                            square.paste(img, offset)
                            sizes = [
                                (16, 16),
                                (24, 24),
                                (32, 32),
                                (48, 48),
                                (64, 64),
                                (128, 128),
                                (256, 256),
                            ]
                            square.save(icon_path, format="ICO", sizes=sizes)
                    except Exception as exc:
                        print(f"Warning: unable to generate icon.ico: {exc}")
    if icon_path and icon_path.exists():
        args.append(f"--icon={icon_path}")

    # Add bundled assets (icons, logo, app shell)
    sep = ";" if PLATFORM == "Windows" else ":"
    asset_files = [
        PROJECT_ROOT / "assets" / "marker_outlined_transparent.png",
        PROJECT_ROOT / "assets" / "marker_ev.png",
        PROJECT_ROOT / "assets" / "everline-horizontal-logo.jpg",
        PROJECT_ROOT / "assets" / "favicon_everline1.ico",
        PROJECT_ROOT / "assets" / "icon.ico",
        PROJECT_ROOT / "assets" / "icon.icns",
        PROJECT_ROOT / "assets" / "app.html",
    ]
    for asset in asset_files:
        if asset.exists():
            args.append(f"--add-data={asset}{sep}assets")

    # Run PyInstaller
    result = subprocess.run(args, cwd=PROJECT_ROOT)

    if result.returncode != 0:
        print("Build failed!")
        sys.exit(1)

    print("Build successful!")


def create_distribution():
    """Create the distribution package."""
    print("Creating distribution package...")

    # Determine executable name and platform suffix
    if PLATFORM == "Windows":
        exe_name = f"{APP_NAME}.exe"
        platform_suffix = "Windows"
    elif PLATFORM == "Darwin":
        exe_name = f"{APP_NAME}.app"
        platform_suffix = "macOS"
    else:
        exe_name = APP_NAME
        platform_suffix = "Linux"

    dist_package_dir = DIST_DIR / f"{APP_NAME}_v{VERSION}_{platform_suffix}"
    dist_package_dir.mkdir(parents=True, exist_ok=True)

    # Copy executable
    exe_path = DIST_DIR / exe_name
    if exe_path.exists():
        if exe_path.is_dir():
            shutil.copytree(exe_path, dist_package_dir / exe_name, dirs_exist_ok=True)
        else:
            shutil.copy(exe_path, dist_package_dir)
            # Make executable on Unix
            if PLATFORM != "Windows":
                (dist_package_dir / exe_name).chmod(0o755)

    # Copy README
    readme_src = PROJECT_ROOT / "README.md"
    readme_dst = dist_package_dir / "README.txt"
    if readme_src.exists():
        shutil.copy(readme_src, readme_dst)

    # Create ZIP archive
    zip_path = DIST_DIR / f"{APP_NAME}_v{VERSION}_{platform_suffix}"
    shutil.make_archive(str(zip_path), 'zip', DIST_DIR, dist_package_dir.name)

    print(f"Distribution created: {zip_path}.zip")

    # Get file sizes
    exe_in_dist = dist_package_dir / exe_name
    if exe_in_dist.exists() and exe_in_dist.is_file():
        exe_size = exe_in_dist.stat().st_size / (1024 * 1024)
        zip_size = Path(f"{zip_path}.zip").stat().st_size / (1024 * 1024)

        print(f"\nBuild complete!")
        print(f"  Platform: {platform_suffix}")
        print(f"  Executable size: {exe_size:.1f} MB")
        print(f"  ZIP package size: {zip_size:.1f} MB")
    else:
        print(f"\nBuild complete! Output in: {dist_package_dir}")


def main():
    """Main build process."""
    print("=" * 50)
    print(f"PicPlotter Auto v{VERSION} Build Script")
    print("=" * 50)
    print()

    # Show platform info
    print(f"Building for: {PLATFORM}")
    if PLATFORM == "Linux":
        print("NOTE: To build a Windows .exe, run this script on Windows.")
    print()

    # Check for PyInstaller
    try:
        import PyInstaller
        print(f"PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("ERROR: PyInstaller not installed!")
        print("Run: pip install pyinstaller")
        sys.exit(1)

    # Check for pillow-heif
    try:
        import pillow_heif
        print("pillow-heif: installed (HEIC support enabled)")
    except ImportError:
        print("pillow-heif: NOT installed (HEIC support disabled)")
        print("To enable HEIC support: pip install pillow-heif")

    print()

    # Build steps
    clean()
    build_executable()
    create_distribution()


if __name__ == "__main__":
    main()
