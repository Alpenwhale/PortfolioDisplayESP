"""Entry point."""
import config
from display import create_display
from app import App

App(create_display(config)).run()
