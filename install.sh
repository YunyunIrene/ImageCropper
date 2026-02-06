#!/bin/bash


echo "Installing ImageCropper..."


sudo apt-get update
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0 \
    python3-cairo


pip3 install Pillow numpy


cat > ~/.local/share/applications/image-cropper.desktop << EOF
[Desktop Entry]
Type=Application
Name=ImageCropper
Comment=A tool to crop Image on Ubuntu System
Exec=python3 $(pwd)/ImageCropper.py
Icon=$(pwd)/icon.png
Terminal=false
Categories=Graphics;GTK;
EOF


cat > image-cropper-launcher.sh << EOF
#!/bin/bash
cd "$(dirname "$0")"
python3 ImageCropper.py
EOF

chmod +x image-cropper-launcher.sh

echo "Install succeed"

