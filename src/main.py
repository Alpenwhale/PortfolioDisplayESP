"""Entry point: build the display from config, hand over to the app."""
import config
from display import create_display
from core.app import App

App(create_display(config)).run()
