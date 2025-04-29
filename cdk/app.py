#!/usr/bin/env python3
import os
from aws_cdk import App
from app_stack import AppStack

app = App()

# Get app name from environment variable
app_name = os.environ.get('APP_NAME')
if not app_name:
    raise ValueError("APP_NAME environment variable is required")

# Deploy the stack
AppStack(app, f"{app_name}Stack",
    app_name=app_name,
    env={
        'account': os.environ.get('CDK_DEFAULT_ACCOUNT'),
        'region': os.environ.get('CDK_DEFAULT_REGION')
    }
)

app.synth() 