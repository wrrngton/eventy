#!/bin/bash
cd /home/ec2-user/apps/eventy
source .venv/bin/activate
python3 script.py --config-dir "fashion"
