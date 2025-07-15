#!/usr/bin/env bash

# Exit on any error
set -e

# Update system packages
apt-get update

# Install system-level build tools and dependencies
apt-get install -y build-essential python3-dev libxml2-dev libxslt-dev

# Upgrade pip and install wheel + setuptools
pip install --upgrade pip setuptools wheel

# Install setuptools explicitly first (for pkg_resources)
pip install setuptools>=65.0.0

# Install dependencies from requirements.txt
pip install -r requirements.txt

echo "Build completed successfully!"
