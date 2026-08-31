[app]

# App name shown on Android home screen
title = Aurora

# Package name — must be unique, like a domain name reversed
package.name = aurora
package.domain = com.parthdhola

# Source directory (where main.py lives)
source.dir = .

# File types to include in the APK
source.include_exts = py,png,jpg,kv,atlas,json

# App version
version = 1.0

# Python packages your app needs (these get bundled into the APK)
requirements = python3,kivy,requests,websocket-client,urllib3,certifi,chardet,idna

# Screen orientation
orientation = portrait

# Android permissions your app needs (Internet + File reading for PDF upload)
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_DOCUMENTS

# Minimum Android API level (API 21 = Android 5.0+)
android.minapi = 21

# Target Android API level
android.api = 33

# App icon (put a 512x512 aurora.png in android-app/ folder, or remove this line)
# icon.filename = %(source.dir)s/aurora.png

# Presplash screen (optional)
# presplash.filename = %(source.dir)s/presplash.png

# Android architecture (arm64-v8a covers most modern phones)
android.archs = arm64-v8a

[buildozer]
# Build log verbosity (2 = verbose, good for debugging)
log_level = 2
warn_on_root = 1
