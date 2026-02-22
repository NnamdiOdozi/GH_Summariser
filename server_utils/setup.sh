#!/bin/bash
# Github Summariser App Update Script
# This script stops the service, updates dependencies, and restarts the service

echo "=== Github Summariser App Update Script ==="
echo "Starting update process at $(date)"
echo

# Stop the github summariser service
echo "?? Stopping GH_summariser.service..."
sudo systemctl stop GH_summariser.service
if [ $? -eq 0 ]; then
    echo "? Successfully stopped GH_summariser.service"
else
    echo "? Failed to stop GH_summariser.service"
    exit 1
fi
echo

# ---- Detect Python ----
PYTHON_BIN=""
for version in python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v $version &> /dev/null; then
        PYTHON_BIN=$version
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "? No suitable Python found. Please install Python 3.9+"
    exit 1
fi

echo "?? Using Python interpreter: $($PYTHON_BIN --version)"

# Set virtual environment and project paths
VENV_PATH="/home/projects/GH_summariser/.venv"
VENV_PYTHON="$VENV_PATH/bin/python"
PROJECT_PATH="/home/projects/GH_summariser"

# Check if virtual environment exists
echo "?? Checking virtual environment..."
if [ ! -d "$VENV_PATH" ]; then
    echo "??  Virtual environment not found at $VENV_PATH"
    echo "?? Creating virtual environment..."
    cd "$PROJECT_PATH" || exit 1
    $PYTHON_BIN -m venv "$VENV_PATH"
    if [ $? -eq 0 ]; then
        echo "? Successfully created virtual environment"
    else
        echo "? Failed to create virtual environment"
        exit 1
    fi

    # Install uv in the new venv
    echo "?? Installing uv in virtual environment..."
    $VENV_PATH/bin/pip install uv
    if [ $? -eq 0 ]; then
        echo "? Successfully installed uv"
    else
        echo "? Failed to install uv"
        exit 1
    fi
else
    if [ ! -f "$VENV_PYTHON" ]; then
        echo "? Python not found in virtual environment at $VENV_PYTHON"
        exit 1
    fi
    echo "? Virtual environment found at $VENV_PATH"
fi

# Activate virtual environment
source "$VENV_PATH/bin/activate"

# Install uv if not available
echo "?? Checking for uv..."
if ! command -v uv &> /dev/null; then
    echo "??  uv not found, installing..."
    pip install uv
    if [ $? -eq 0 ]; then
        echo "? uv installed"
    else
        echo "? Failed to install uv"
        exit 1
    fi
else
    echo "? uv already available"
fi

# Sync dependencies with uv
echo "?? Syncing dependencies with uv..."
cd "$PROJECT_PATH" || exit 1
uv sync
if [ $? -eq 0 ]; then
    echo "? Successfully synced dependencies"
else
    echo "? Failed to sync dependencies"
    exit 1
fi

# Install gitingest if not already installed
echo "?? Checking gitingest installation..."
if ! command -v gitingest &> /dev/null && ! uvx gitingest --version &> /dev/null; then
    echo "??  gitingest not found, installing..."
    pip install gitingest
    if [ $? -eq 0 ]; then
        echo "? gitingest installed"
    else
        echo "? Warning: Failed to install gitingest"
    fi
else
    echo "? gitingest already available"
fi
echo

# Reload systemd daemon
echo "?? Reloading systemd daemon..."
sudo systemctl daemon-reload
if [ $? -eq 0 ]; then
    echo "? Successfully reloaded systemd daemon"
else
    echo "?? Warning: Failed to reload systemd daemon"
fi

# Restart the github summariser service
echo "?? Starting GH_summariser.service..."
sudo systemctl start GH_summariser.service
if [ $? -eq 0 ]; then
    echo "? Successfully started GH_summariser.service"
else
    echo "? Failed to start GH_summariser.service"
    exit 1
fi
echo

# Check service status
echo "?? Checking service status..."
sudo systemctl status GH_summariser.service --no-pager -l
echo

echo "=== Update process completed successfully at $(date) ==="
echo "Github Summariser App has been updated and restarted!"
