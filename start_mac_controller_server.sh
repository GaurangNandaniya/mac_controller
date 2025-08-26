#!/bin/bash
cd $macControllerDirPath #you will have to do export macControllerDirPath="your_path_here_to_project" in zshrc 
source venv/bin/activate
python3 mac_controller_app.py