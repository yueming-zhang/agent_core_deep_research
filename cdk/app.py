#!/usr/bin/env python3

from deep_research_stack import DeepResearchStack
import aws_cdk as cdk
import warnings
warnings.filterwarnings('ignore', message='Typeguard cannot check.*protocol')

app = cdk.App()
DeepResearchStack(app, "DeepResearch")

app.synth()
